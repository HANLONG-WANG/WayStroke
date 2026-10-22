//! XWayland text without an accessible editor. The keyword is selected with
//! Shift+Left and replaced only after reading back exactly that text.
//! Keys come from the extension's virtual keyboard; XWayland raw events give
//! their delivery order. Only a short tail of typed text is kept, in memory.
use std::{collections::{HashMap,VecDeque},sync::{Arc,Mutex as Shared},time::{Duration,Instant}};
use serde::Deserialize;
use serde_json::{Value,json};
use tokio::sync::{Mutex,Notify};
use x11rb::{connection::Connection,protocol::{Event,xfixes::{self,ConnectionExt as _},xinput::{self,ConnectionExt as _},xproto::{self,Atom,AtomEnum,ConnectionExt as _,EventMask,PropMode,Window}},rust_connection::{DefaultStream,RustConnection},wrapper::ConnectionExt as _};
use waystroke_model::Config;
use waystroke_protocol::{Error,ErrorKind,TextInputTrigger,TextMatchRequest};
use crate::{atspi::Guard,desktop::Desktop,error};

/// Predefined atom XA_PRIMARY.
const PRIMARY:Atom=1;
const COPY:u32=0x63;
const SHIFT:u32=0xffe1;const LEFT:u32=0xff51;const RIGHT:u32=0xff53;const BACKSPACE:u32=0xff08;const PASTE:u32=0x76;
/// Owner change after the first selection key; a frozen or non-exporting
/// client costs at most this long.
const PROBE:Duration=Duration::from_millis(150);
const VERIFY:Duration=Duration::from_millis(300);
/// Without a known character before the keyword, a selection that stops at
/// the keyword is either the field start or a slow client; see `boundary`.
const SETTLE:Duration=Duration::from_millis(60);
const DELIVERY:Duration=Duration::from_millis(400);
/// After this many consecutive windows without an exported selection the
/// window is skipped, so a non-text client sees at most a few key pairs.
const PROBE_FAILURES:u8=3;
const TAIL:usize=128;
/// X11 terminals turn Shift+arrows into escape sequences for their program.
const TERMINALS:&[&str]=&["xterm","uxterm","urxvt","rxvt","st","st-256color","alacritty","kitty","terminator","xfce4-terminal","gnome-terminal","gnome-terminal-server","konsole","tilix","sakura","guake","tilda","termite","wezterm","org.wezfurlong.wezterm","foot","eterm","aterm","mlterm","lxterminal","mate-terminal","qterminal","cool-retro-term","terminology","yakuake","ptyxis","org.gnome.ptyxis","kgx","org.gnome.console","ghostty","com.mitchellh.ghostty","contour","zutty","tabby","hyper","deepin-terminal","x-terminal-emulator"];
pub fn terminal(class:&str)->bool{TERMINALS.contains(&class.to_lowercase().as_str())}

#[derive(Clone,Copy)]
/// A delivered press: its first two keysym levels identify our own keys
/// independently of which keycode the virtual keyboard chose.
struct Press {syms:[u32;2],char:Option<char>,modifier:bool}
#[derive(Default)]
struct Keymap {min:u8,per:u8,syms:Vec<u32>}
impl Keymap {
    fn sym(&self,code:u8,level:usize)->u32{
        if code<self.min||level>=self.per as usize{return 0}
        self.syms.get((code-self.min) as usize*self.per as usize+level).copied().unwrap_or(0)
    }
    /// Keys the virtual keyboard can type without AltGr; deeper levels paste.
    fn typable(&self,sym:u32)->bool{
        (self.min..=self.min.saturating_add((self.syms.len()/self.per.max(1) as usize).saturating_sub(1) as u8)).any(|code|(0..2.min(self.per as usize)).any(|level|self.sym(code,level)==sym))
    }
}
fn modifier(sym:u32)->bool{(0xffe1..=0xffee).contains(&sym)||matches!(sym,0xfe03|0xff7e)}
fn keysym_char(sym:u32)->Option<char>{
    match sym {
        0x20..=0x7e|0xa0..=0xff=>char::from_u32(sym),
        0x0100_0100..=0x0110_ffff=>char::from_u32(sym-0x0100_0000),
        0xffb0..=0xffb9=>char::from_u32(sym-0xffb0+'0' as u32),
        0xffaa=>Some('*'),0xffab=>Some('+'),0xffad=>Some('-'),0xffae=>Some('.'),0xffaf=>Some('/'),0xff80=>Some(' '),
        _=>None,
    }
}
/// Toolkits move the caret by grapheme; a keyword whose characters are all
/// single code points makes every shorter, intermediate selection distinct.
fn simple(c:char)->bool{
    let v=c as u32;
    v<0x10000&&!matches!(v,0x0300..=0x036f|0x0483..=0x0489|0x0591..=0x05c7|0x0610..=0x061a|0x064b..=0x065f|0x0900..=0x0dff|0x0e31..=0x0e4e|0x1ab0..=0x1aff|0x1dc0..=0x1dff|0x200b..=0x200f|0x20d0..=0x20ff|0xfe00..=0xfe0f|0xfe20..=0xfe2f|0xd800..=0xdfff)
}

/// Caret steps in `text`: toolkits move over a base character together with
/// combining marks, variation selectors, emoji modifiers, ZWJ sequences and
/// regional-indicator pairs.
fn graphemes(text:&str)->usize{
    let (mut count,mut join,mut flag)=(0,false,false);
    for c in text.chars(){
        let v=c as u32;
        if matches!(v,0x0300..=0x036f|0x1ab0..=0x1aff|0x1dc0..=0x1dff|0x20d0..=0x20ff|0xfe00..=0xfe0f|0xfe20..=0xfe2f|0x200d|0x1f3fb..=0x1f3ff|0xe0020..=0xe007f){join=c=='\u{200d}';continue}
        let indicator=(0x1f1e6..=0x1f1ff).contains(&v);
        if join||indicator&&flag{join=false;flag=false;continue}
        flag=indicator;count+=1;
    }
    count
}
#[derive(Default)]
struct State {
    presses:VecDeque<Press>,total:u64,
    typed:String,known:bool,before:Option<char>,
    held:Vec<u32>,caps:bool,busy:bool,
    owners:u64,notifies:u64,notified:Atom,marker:u32,dead:bool,
    serving:HashMap<Atom,String>,keymap:Keymap,
}
impl State {
    fn reset(&mut self){self.typed.clear();self.known=false;self.before=None}
    fn key(&mut self,code:u8,pressed:bool){
        let base=self.keymap.sym(code,0);
        if modifier(base){
            if pressed{if !self.held.contains(&base){self.held.push(base)}if base==0xffe5{self.caps=!self.caps}}else{self.held.retain(|&held|held!=base)}
            if pressed{self.record(Press{syms:[base,base],char:None,modifier:true})}return;
        }
        if !pressed{return}
        let shift=self.held.iter().any(|&sym|matches!(sym,0xffe1|0xffe2));
        let letter=matches!(base,0x61..=0x7a|0xe0..=0xf6|0xf8..=0xfe);
        let level=usize::from(shift^(self.caps&&letter))+if self.held.iter().any(|&sym|matches!(sym,0xfe03|0xff7e)){2}else{0};
        let sym=match self.keymap.sym(code,level){0=>self.keymap.sym(code,level&1),sym=>sym};
        let char=keysym_char(sym);self.record(Press{syms:[base,self.keymap.sym(code,1)],char,modifier:false});
        if self.busy{return}
        if self.held.iter().any(|&sym|matches!(sym,0xffe3|0xffe4|0xffe7..=0xffee)){self.reset();return}
        if sym==BACKSPACE{if self.typed.pop().is_none(){self.known=false;self.before=None}return}
        match char {
            Some(c)=>{
                self.typed.push(c);
                if self.typed.chars().count()>TAIL{let cut=self.typed.char_indices().nth(TAIL/2).unwrap().0;self.before=self.typed[..cut].chars().next_back();self.known=true;self.typed.drain(..cut);}
            },
            None=>self.reset(),
        }
    }
    fn record(&mut self,press:Press){self.presses.push_back(press);self.total+=1;if self.presses.len()>512{self.presses.pop_front();}}
    fn since(&self,index:u64)->Vec<Press>{let first=self.total-self.presses.len() as u64;self.presses.iter().skip(index.saturating_sub(first) as usize).copied().collect()}
}

struct Atoms {utf8:Atom,targets:Atom,property:Atom,sync:Atom,active:Atom}
struct X {conn:RustConnection,window:Window,atoms:Atoms,state:Shared<State>,changed:Notify,display:String}
fn x_error(e:impl std::fmt::Display)->Error{error(ErrorKind::Unavailable,format!("XWayland 接入失败：{e}"))}
/// Mutter's MIT cookie file; the core process cannot rely on its own
/// environment because XWayland starts on demand.
fn cookie(path:&str,display:&str)->Result<(Vec<u8>,Vec<u8>),Error>{
    let data=std::fs::read(path).map_err(x_error)?;let number=display.trim_start_matches(|c|c!=':').trim_start_matches(':').split('.').next().unwrap_or("");
    // Entries: family u16, then address, display number, name and data,
    // each a big-endian u16 length followed by its bytes.
    let take=|rest:&mut &[u8]|->Option<Vec<u8>>{if rest.len()<2{return None}let n=u16::from_be_bytes([rest[0],rest[1]]) as usize;if rest.len()<2+n{return None}let v=rest[2..2+n].to_vec();*rest=&rest[2+n..];Some(v)};
    let mut rest=&data[..];
    while rest.len()>=2 {
        rest=&rest[2..];
        let (Some(_address),Some(entry),Some(name),Some(secret))=(take(&mut rest),take(&mut rest),take(&mut rest),take(&mut rest)) else{break};
        if name==b"MIT-MAGIC-COOKIE-1"&&(entry.is_empty()||entry==number.as_bytes()){return Ok((name,secret))}
    }
    Err(error(ErrorKind::Unavailable,"XWayland 认证文件中没有可用的凭据"))
}
impl X {
    fn open(display:&str,xauthority:Option<&str>)->Result<Arc<X>,Error>{
        let conn=match xauthority {
            Some(path)=>{
                let parsed=x11rb::reexports::x11rb_protocol::parse_display::parse_display(Some(display)).map_err(x_error)?;
                let stream=parsed.connect_instruction().find_map(|address|DefaultStream::connect(&address).ok()).ok_or_else(||error(ErrorKind::Unavailable,"无法连接 XWayland"))?.0;
                let (name,secret)=cookie(path,display)?;
                RustConnection::connect_to_stream_with_auth_info(stream,parsed.screen.into(),name,secret).map_err(x_error)?
            },
            None=>RustConnection::connect(Some(display)).map_err(x_error)?.0,
        };
        conn.xinput_xi_query_version(2,2).map_err(x_error)?.reply().map_err(x_error)?;
        conn.xfixes_query_version(5,0).map_err(x_error)?.reply().map_err(x_error)?;
        let root=conn.setup().roots[0].root;let window=conn.generate_id().map_err(x_error)?;
        conn.create_window(0,window,root,0,0,1,1,0,xproto::WindowClass::INPUT_ONLY,0,&Default::default()).map_err(x_error)?;
        let atom=|name:&str|->Result<Atom,Error>{Ok(conn.intern_atom(false,name.as_bytes()).map_err(x_error)?.reply().map_err(x_error)?.atom)};
        let atoms=Atoms{utf8:atom("UTF8_STRING")?,targets:atom("TARGETS")?,property:atom("WAYSTROKE_SELECTION")?,sync:atom("WAYSTROKE_SYNC")?,active:atom("_NET_ACTIVE_WINDOW")?};
        // Raw events arrive only while an X11 window has keyboard focus.
        conn.xinput_xi_select_events(root,&[xinput::EventMask{deviceid:xinput::Device::ALL_MASTER.into(),mask:vec![xinput::XIEventMask::RAW_KEY_PRESS|xinput::XIEventMask::RAW_KEY_RELEASE|xinput::XIEventMask::RAW_BUTTON_PRESS]}]).map_err(x_error)?;
        conn.xfixes_select_selection_input(root,PRIMARY,xfixes::SelectionEventMask::SET_SELECTION_OWNER).map_err(x_error)?;
        conn.change_window_attributes(root,&xproto::ChangeWindowAttributesAux::new().event_mask(EventMask::PROPERTY_CHANGE)).map_err(x_error)?;
        let x=Arc::new(X{conn,window,atoms,state:Shared::new(State::default()),changed:Notify::new(),display:display.into()});
        x.keymap()?;
        let events=x.clone();std::thread::Builder::new().name("waystroke-xwayland".into()).spawn(move||events.events()).map_err(x_error)?;
        Ok(x)
    }
    fn keymap(&self)->Result<(),Error>{
        let setup=self.conn.setup();let (min,max)=(setup.min_keycode,setup.max_keycode);
        let reply=self.conn.get_keyboard_mapping(min,max-min+1).map_err(x_error)?.reply().map_err(x_error)?;
        self.state.lock().unwrap().keymap=Keymap{min,per:reply.keysyms_per_keycode,syms:reply.keysyms};Ok(())
    }
    fn events(self:Arc<Self>){
        loop {
            let Ok(event)=self.conn.wait_for_event() else{self.state.lock().unwrap().dead=true;self.changed.notify_waiters();return};
            match event {
                Event::XinputRawKeyPress(e)=>self.state.lock().unwrap().key(e.detail as u8,true),
                Event::XinputRawKeyRelease(e)=>self.state.lock().unwrap().key(e.detail as u8,false),
                Event::XinputRawButtonPress(_)=>self.state.lock().unwrap().reset(),
                Event::PropertyNotify(e) if e.atom==self.atoms.active=>self.state.lock().unwrap().reset(),
                Event::XfixesSelectionNotify(e) if e.owner!=self.window=>self.state.lock().unwrap().owners+=1,
                Event::SelectionNotify(e) if e.requestor==self.window=>{let mut state=self.state.lock().unwrap();state.notifies+=1;state.notified=e.property;},
                Event::SelectionRequest(e)=>{let text=self.state.lock().unwrap().serving.get(&e.selection).cloned();if let Err(error)=self.answer(e,text){eprintln!("XWayland 选区应答失败：{}",error.message)}},
                Event::MappingNotify(e) if e.request==xproto::Mapping::KEYBOARD=>{if let Err(error)=self.keymap(){eprintln!("XWayland 键盘映射刷新失败：{}",error.message)}},
                Event::ClientMessage(e) if e.type_==self.atoms.sync=>{let data=e.data.as_data32();if data[1]==1{return}self.state.lock().unwrap().marker=data[0];},
                _=>continue,
            }
            self.changed.notify_waiters();
        }
    }
    fn answer(&self,request:xproto::SelectionRequestEvent,text:Option<String>)->Result<(),Error>{
        let property=if request.property==0{request.target}else{request.property};
        let property=match text {
            Some(_) if request.target==self.atoms.targets=>{self.conn.change_property32(PropMode::REPLACE,request.requestor,property,AtomEnum::ATOM,&[self.atoms.targets,self.atoms.utf8,AtomEnum::STRING.into()]).map_err(x_error)?;property},
            Some(text) if request.target==self.atoms.utf8||request.target==u32::from(AtomEnum::STRING)=>{self.conn.change_property8(PropMode::REPLACE,request.requestor,property,request.target,text.as_bytes()).map_err(x_error)?;property},
            _=>0,
        };
        self.conn.send_event(false,request.requestor,EventMask::NO_EVENT,xproto::SelectionNotifyEvent{response_type:xproto::SELECTION_NOTIFY_EVENT,sequence:0,time:request.time,requestor:request.requestor,selection:request.selection,target:request.target,property}).map_err(x_error)?;
        self.conn.flush().map_err(x_error)
    }
    fn close(&self){
        let _=self.conn.send_event(false,self.window,EventMask::NO_EVENT,xproto::ClientMessageEvent::new(32,self.window,self.atoms.sync,[0,1,0,0,0]));let _=self.conn.flush();
    }
    async fn until<T>(&self,deadline:Instant,mut check:impl FnMut(&State)->Option<T>)->Option<T>{
        loop {
            let notified=self.changed.notified();tokio::pin!(notified);notified.as_mut().enable();
            {let state=self.state.lock().unwrap();if let Some(value)=check(&state){return Some(value)}if state.dead{return None}}
            if tokio::time::timeout_at(deadline.into(),notified).await.is_err(){return None}
        }
    }
    /// Events queued by XWayland before this request are handled once the
    /// marker returns, so the typed tail is current when a trigger arrives.
    async fn sync(&self)->Result<(),Error>{
        let marker={let mut state=self.state.lock().unwrap();state.marker=state.marker.wrapping_add(1);state.marker};
        self.conn.send_event(false,self.window,EventMask::NO_EVENT,xproto::ClientMessageEvent::new(32,self.window,self.atoms.sync,[marker,0,0,0,0])).map_err(x_error)?;self.conn.flush().map_err(x_error)?;
        self.until(Instant::now()+Duration::from_millis(200),|state|(state.marker==marker).then_some(())).await.ok_or_else(||error(ErrorKind::Timeout,"XWayland 事件同步超时"))
    }
    fn own(&self,text:String)->Result<(),Error>{
        self.state.lock().unwrap().serving.insert(PRIMARY,text);
        self.conn.set_selection_owner(self.window,PRIMARY,x11rb::CURRENT_TIME).map_err(x_error)?;self.conn.flush().map_err(x_error)
    }
    async fn read(&self,deadline:Instant)->Option<String>{
        let count=self.state.lock().unwrap().notifies;
        self.conn.convert_selection(self.window,PRIMARY,self.atoms.utf8,self.atoms.property,x11rb::CURRENT_TIME).ok()?;self.conn.flush().ok()?;
        let property=self.until(deadline,|state|(state.notifies>count).then_some(state.notified)).await?;
        if property==0{return None}
        let reply=self.conn.get_property(true,self.window,self.atoms.property,AtomEnum::ANY,0,1<<16).ok()?.reply().ok()?;
        if reply.type_!=self.atoms.utf8&&reply.type_!=u32::from(AtomEnum::STRING){return None}
        Some(String::from_utf8_lossy(&reply.value).into_owned())
    }
    fn restore_primary(&self,previous:Option<String>)->Result<(),Error>{
        match previous.filter(|text|!text.is_empty()) {
            Some(text)=>self.own(text),
            None=>{
                if self.conn.get_selection_owner(PRIMARY).map_err(x_error)?.reply().map_err(x_error)?.owner==self.window{self.conn.set_selection_owner(x11rb::NONE,PRIMARY,x11rb::CURRENT_TIME).map_err(x_error)?;self.conn.flush().map_err(x_error)?}
                Ok(())
            },
        }
    }
}

/// Our own non-modifier presses, matched in order against delivered raw
/// presses. XWayland has one device for every source, so the user's keys are
/// the presses that do not match. Returns (matched count, foreign presses with
/// how many of ours preceded each).
fn align(presses:&[Press],ours:&[u32])->(usize,Vec<(usize,Press)>){
    let mut matched=0;let mut foreign=vec![];
    for press in presses.iter().filter(|press|!press.modifier){
        if matched<ours.len()&&press.syms.contains(&ours[matched]){matched+=1}else{foreign.push((matched,*press))}
    }
    (matched,foreign)
}
/// What the client holds after foreign printable presses landed inside the
/// selection or among our typed replacement keys, in delivery order.
fn interleave(selection:usize,replacement:&str,foreign:&[(usize,Press)])->Option<String>{
    let mut held=String::new();let mut typed=replacement.chars();let mut foreign=foreign.iter().peekable();
    for index in 0..=replacement.chars().count(){
        while let Some((position,press))=foreign.peek(){if *position>selection+index{break}held.push(press.char?);foreign.next();}
        if let Some(c)=typed.next(){held.push(c)}
    }
    for (_,press) in foreign{held.push(press.char?)}
    Some(held)
}

#[derive(Deserialize)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct Prepare {pub active:bool,pub display:Option<String>,pub xauthority:Option<String>}
struct Undo {token:String,guard:Guard,held:String,restore:String,after:u64}
enum Edit {Type(Vec<(u32,bool)>),Paste(String)}
#[derive(Default)]
pub struct Adapter {x:Mutex<Option<Arc<X>>>,editing:Mutex<()>,failures:Mutex<HashMap<String,u8>>,undo:Mutex<Option<Undo>>}
fn keys(keyval:u32,count:usize,shift:bool)->Vec<(u32,bool)>{
    let mut out=vec![];if shift{out.push((SHIFT,true))}
    for _ in 0..count{out.push((keyval,true));out.push((keyval,false))}
    if shift{out.push((SHIFT,false))}out
}
fn unmodified(mut error:Error)->Error{error.details.push(waystroke_model::ValidationError{path:"text.unmodified".into(),message:"尚未发出编辑按键，可恢复原确认键".into()});error}
fn partial(mut error:Error)->Error{error.details.push(waystroke_model::ValidationError{path:"text.partialEdit".into(),message:"已发出选区或编辑按键；停止重放确认键".into()});error}
fn window_key(guard:&Guard)->String{format!("{}:{}",guard.window.instance,guard.window.id)}
impl Adapter {
    pub async fn prepare(&self,request:Prepare)->Result<(),Error>{
        let mut slot=self.x.lock().await;
        if let Some(x)=slot.as_ref(){
            let current=request.active&&!x.state.lock().unwrap().dead&&request.display.as_deref()==Some(x.display.as_str());
            if current{x.state.lock().unwrap().reset();return Ok(())}
            x.close();*slot=None;*self.undo.lock().await=None;
        }
        let (true,Some(display))=(request.active,request.display) else{return Ok(())};
        let xauthority=request.xauthority;
        *slot=Some(tokio::task::spawn_blocking(move||X::open(&display,xauthority.as_deref())).await.map_err(x_error)??);Ok(())
    }
    pub async fn clear(&self,token:&str)->bool{let mut undo=self.undo.lock().await;if undo.as_ref().is_some_and(|entry|entry.token==token){*undo=None;true}else{false}}
    async fn connection(&self)->Option<Arc<X>>{self.x.lock().await.clone().filter(|x|!x.state.lock().unwrap().dead)}
    async fn send(desktop:&Desktop,guard:&Guard,events:&[(u32,bool)])->Result<(),Error>{
        desktop.call(json!({"operation":"textKeys","guard":guard,"keys":events.iter().map(|(keyval,pressed)|json!([keyval,pressed])).collect::<Vec<_>>()})).await.map(|_|())
    }
    /// WeChat sets neither PRIMARY nor any other selection for keyboard or
    /// mouse selections, only CLIPBOARD on Ctrl+C. Copy shortcuts are never
    /// sent to other clients (a raw terminal would get an interrupt).
    fn copy_only(guard:&Guard)->bool{matches!(guard.wm_class.to_lowercase().as_str(),"wechat"|"weixin")}
    /// Claim PRIMARY so any exporting widget must take it again, then select
    /// back `count` positions and read until PRIMARY equals `expected`. A
    /// probe sends one key first and stops if the client exports nothing.
    /// A copy-only editor selects `extra` more and is read by a single copy,
    /// which Shell restores with every clipboard format; Ctrl+C follows the
    /// Shift+Left presses through the same keyboard, so it sees all of them.
    async fn select(x:&X,desktop:&Desktop,guard:&Guard,expected:&str,count:usize,probe:bool,extra:usize)->Result<Selection,Error>{
        let start=Instant::now();x.own(String::new())?;
        let (owners,first)={let state=x.state.lock().unwrap();(state.owners,state.total)};
        if Self::copy_only(guard){
            let mut sent=vec![LEFT;count+extra];Self::send(desktop,guard,&keys(LEFT,count+extra,true)).await?;sent.push(COPY);
            let text=desktop.call(json!({"operation":"clipboardReadSelection","guard":guard})).await?.as_str().map(String::from);
            crate::atspi::Adapter::guard(desktop,guard).await?;
            return Ok(Selection{first,exported:text.is_some(),text,sent});
        }
        let first_batch=if probe{1}else{count};
        Self::send(desktop,guard,&keys(LEFT,first_batch,true)).await?;
        if x.until(start+PROBE,|state|(state.owners>owners).then_some(())).await.is_none(){return Ok(Selection{first,exported:false,text:None,sent:vec![LEFT;first_batch]})}
        if count>first_batch{Self::send(desktop,guard,&keys(LEFT,count-first_batch,true)).await?}
        let sent=vec![LEFT;count];
        // Tk, Swing and GTK answer selection requests before handling queued
        // keys. The selection only grows, and with single-code-point text a
        // shorter intermediate selection never equals the expected text.
        let deadline=Instant::now()+VERIFY;let mut text=None;
        while Instant::now()<deadline {
            if align(&x.state.lock().unwrap().since(first),&sent).0==count{text=x.read(deadline).await;if text.as_deref()==Some(expected){break}}
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        Ok(Selection{first,exported:true,text,sent})
    }
    async fn shift(desktop:&Desktop,guard:&Guard,keyval:u32,count:usize,sent:&mut Vec<u32>)->Result<(),Error>{
        if count==0{return Ok(())}
        Self::send(desktop,guard,&keys(keyval,count,true)).await?;
        sent.extend(std::iter::repeat_n(keyval,count));Ok(())
    }
    /// With the keyword verified, one more Shift+Left shows the character
    /// before it. A selection that stays at the keyword is the field start
    /// only if one Shift+Right then shrinks it: a slow client that still has
    /// the extra Shift+Left queued never shows the shorter selection.
    async fn boundary(x:&X,desktop:&Desktop,guard:&Guard,keyword:&str,sent:&mut Vec<u32>)->Result<Boundary,Error>{
        let count=keyword.chars().count();
        Self::shift(desktop,guard,LEFT,1,sent).await?;
        let deadline=Instant::now()+SETTLE;
        while Instant::now()<deadline {
            if let Some(text)=x.read(deadline).await.filter(|text|text.chars().count()==count+1&&text.ends_with(keyword)){
                if text.chars().next().is_some_and(|c|c.is_alphanumeric()||c=='_'){return Ok(Boundary::Word)}
                Self::shift(desktop,guard,RIGHT,1,sent).await?;return Ok(Boundary::Separated);
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        Self::shift(desktop,guard,RIGHT,1,sent).await?;
        let shorter:String=keyword.chars().skip(1).collect();let deadline=Instant::now()+VERIFY;
        while Instant::now()<deadline {
            if x.read(deadline).await.as_deref()==Some(shorter.as_str()){Self::shift(desktop,guard,LEFT,1,sent).await?;return Ok(Boundary::FieldStart)}
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        Ok(Boundary::Unknown)
    }
    /// Undo the Shift+Left presses. Tk cannot shrink a selection across
    /// a multi-code-point character just before the caret; a plain Right and
    /// Left then clears it (one position early only at the text end), so the
    /// next key cannot replace that character.
    /// The observed selection is the final one: callers reach this only after
    /// the read budget. A shorter selection stopped at the field start, and
    /// more Shift+Right presses would select text after the original caret.
    async fn unselect(desktop:&Desktop,guard:&Guard,count:usize,observed:Option<&str>)->Result<(),Error>{
        let count=observed.map_or(count,|text|graphemes(text).min(count));
        let mut events=keys(RIGHT,count,true);
        if guard.wm_class=="Tk"&&observed.and_then(|text|text.chars().last()).is_some_and(|c|!simple(c)){events.extend(keys(RIGHT,1,false));events.extend(keys(LEFT,1,false))}
        Self::send(desktop,guard,&events).await
    }
    fn edit(x:&X,text:&str)->Edit{
        let keymap=&x.state.lock().unwrap().keymap;
        if text.chars().all(|c|(' '..='~').contains(&c)&&keymap.typable(c as u32)){Edit::Type(text.chars().flat_map(|c|[(c as u32,true),(c as u32,false)]).collect())}else{Edit::Paste(text.into())}
    }
    /// Sends the edit and returns our expected non-modifier presses for it.
    async fn apply(desktop:&Desktop,guard:&Guard,edit:&Edit)->Result<Vec<u32>,Error>{
        match edit {
            Edit::Type(events)=>{Self::send(desktop,guard,events).await?;Ok(events.iter().filter(|(_,pressed)|*pressed).map(|(keyval,_)|*keyval).collect())},
            Edit::Paste(text)=>{
                // Tk inserts a paste at the caret without replacing the
                // selection, so the selection is deleted first.
                Self::send(desktop,guard,&keys(BACKSPACE,1,false)).await?;
                desktop.clipboard_transaction(json!({"operation":"clipboardPasteStart","window":guard.window,"text":text,"restore":true}),true,DELIVERY.as_millis() as u64).await?;
                Ok(vec![BACKSPACE,PASTE])
            },
        }
    }
    pub async fn expand(&self,session:&zbus::Connection,config:&Config,guard:Guard,trigger:TextInputTrigger,literal:Option<String>)->Result<Value,Error>{
        let _editing=self.editing.lock().await;
        let compatible=!config.exclusions.iter().any(|entry|entry.application_id==guard.application_id&&(entry.text||entry.compatibility));
        if !compatible||terminal(&guard.wm_class){return Ok(json!({"matched":false}))}
        let Some(x)=self.connection().await else{return Ok(json!({"matched":false,"reason":"XWayland 兼容替换尚未连接"}))};
        x.sync().await.map_err(unmodified)?;
        let (typed,known,before)={let state=x.state.lock().unwrap();(state.typed.clone(),state.known,state.before)};
        let before_cursor=before.into_iter().chain(typed.chars()).chain(literal.iter().flat_map(|text|text.chars())).collect::<String>();
        let Some(expansion)=crate::text::match_text(config,&TextMatchRequest{application_id:guard.application_id.clone(),before_cursor,trigger:trigger.clone(),composing:false,password:false,terminal:false}) else{return Ok(json!({"matched":false}))};
        let held:String=expansion.keyword.chars().take(expansion.keyword.chars().count()-literal.as_ref().map_or(0,|text|text.chars().count())).collect();
        let count=held.chars().count();
        if count==0||!held.chars().all(simple){return Ok(json!({"matched":false,"reason":"关键词含组合字符或只有末字符，兼容替换无法逐字校验"}))}
        let window=window_key(&guard);
        if self.failures.lock().await.get(&window).is_some_and(|&failures|failures>=PROBE_FAILURES){return Ok(json!({"matched":false,"reason":"此窗口不导出选区，兼容替换已停用"}))}
        let literal_count=literal.as_ref().map_or(0,|text|text.chars().count());
        let rule_boundary=config.snippets.iter().find(|rule|rule.id==expansion.rule_id).is_some_and(|rule|rule.boundary);
        let unknown_start=rule_boundary&&!known&&expansion.delete_chars as usize>=typed.chars().count()+literal_count;
        if unknown_start&&count<2{return Ok(json!({"matched":false,"reason":"单字符关键词前的文字未知，兼容替换无法确认边界"}))}
        let desktop=Desktop::new(session.clone());
        crate::atspi::Adapter::guard(&desktop,&guard).await.map_err(unmodified)?;
        let previous=x.read(Instant::now()+Duration::from_millis(50)).await;
        let result={let _busy=Busy::new(&x);self.replace(&x,&desktop,&guard,&held,unknown_start,&expansion,trigger,literal.is_some()).await};
        // Hand PRIMARY back; the keyword selection was only ours to verify.
        if let Err(e)=x.restore_primary(previous){eprintln!("PRIMARY 恢复失败：{}",e.message)}
        match &result {
            Ok(value) if value["exported"]==false=>{
                let mut failures=self.failures.lock().await;let entry=failures.entry(window).or_default();*entry+=1;
                let mut value=value.clone();value.as_object_mut().unwrap().remove("exported");
                if *entry==PROBE_FAILURES{value["unsupported"]=json!(true)}return Ok(value);
            },
            Ok(value) if value["matched"]==true=>{self.failures.lock().await.remove(&window);},
            _=>{},
        }
        result
    }
    #[allow(clippy::too_many_arguments)]
    async fn replace(&self,x:&X,desktop:&Desktop,guard:&Guard,held:&str,unknown_start:bool,expansion:&waystroke_protocol::TextExpansion,trigger:TextInputTrigger,literal:bool)->Result<Value,Error>{
        let count=held.chars().count();
        let extra=usize::from(unknown_start&&Self::copy_only(guard));
        let selection=Self::select(x,desktop,guard,held,count,true,extra).await.map_err(partial)?;
        let mut sent=selection.sent.clone();
        let restore=|sent:&Vec<u32>|sent.iter().filter(|&&sym|sym==LEFT).count()-sent.iter().filter(|&&sym|sym==RIGHT).count();
        if !selection.exported{
            Self::send(desktop,guard,&keys(RIGHT,restore(&sent),true)).await.map_err(partial)?;x.state.lock().unwrap().reset();
            return Ok(json!({"matched":false,"exported":false,"reason":"此窗口没有导出选区，未编辑"}));
        }
        // A copy with one extra character also shows what precedes the
        // keyword; exactly the keyword means the field start stopped it.
        let word=selection.text.as_deref().filter(|text|extra==1&&text.chars().count()==count+1&&text.ends_with(held)).map(|text|text.chars().next().is_some_and(|c|c.is_alphanumeric()||c=='_'));
        if word.is_none()&&selection.text.as_deref()!=Some(held){
            x.state.lock().unwrap().reset();
            // A key typed into an unverified selection replaced text we never
            // confirmed; Shift+Right would now select the user's other text.
            if !align(&x.state.lock().unwrap().since(selection.first),&sent).1.is_empty(){return Ok(json!({"matched":false,"failed":"替换校验期间检测到其他输入，未编辑；关键词可能已被该输入覆盖"}))}
            Self::unselect(desktop,guard,count+extra,selection.text.as_deref()).await.map_err(partial)?;
            return Ok(json!({"matched":false,"reason":"选中的文字与关键词不一致，已还原"}));
        }
        match word {
            Some(true)=>{Self::send(desktop,guard,&keys(RIGHT,restore(&sent),true)).await.map_err(partial)?;return Ok(json!({"matched":false}))},
            Some(false)=>Self::shift(desktop,guard,RIGHT,1,&mut sent).await.map_err(partial)?,
            None=>{},
        }
        if unknown_start&&extra==0 {
            match Self::boundary(x,desktop,guard,held,&mut sent).await.map_err(partial)? {
                Boundary::Separated|Boundary::FieldStart=>{},
                Boundary::Word=>{Self::send(desktop,guard,&keys(RIGHT,restore(&sent),true)).await.map_err(partial)?;return Ok(json!({"matched":false}))},
                // Most likely a slow client whose extra Shift+Left and
                // Shift+Right both apply, leaving the verified keyword.
                Boundary::Unknown=>{Self::send(desktop,guard,&keys(RIGHT,count,true)).await.map_err(partial)?;x.state.lock().unwrap().reset();return Ok(json!({"matched":false,"failed":"无法确认关键词前的字符，已还原选区"}))},
            }
        }
        let space=trigger==TextInputTrigger::Space&&expansion.preserve;
        let text=format!("{}{}",expansion.replacement,if space{" "}else{""});
        let edit=Self::edit(x,&text);
        let selected=sent.len();let mut ours=sent;
        ours.extend(Self::apply(desktop,guard,&edit).await.map_err(partial)?);
        if x.until(Instant::now()+DELIVERY,|state|(align(&state.since(selection.first),&ours).0==ours.len()).then_some(())).await.is_none(){return Err(partial(error(ErrorKind::Timeout,"替换按键未被 XWayland 确认送达")))}
        tokio::time::sleep(Duration::from_millis(20)).await;
        let (after,foreign)={let state=x.state.lock().unwrap();(state.total,align(&state.since(selection.first),&ours).1)};
        let mut result=json!({"matched":true,"preserve":expansion.preserve,"confirmationHandled":space||literal,"adapter":"selection","ruleId":expansion.rule_id});
        // Keys delivered after our edit are already in typing order; earlier
        // ones landed in the selection or among the replacement keys.
        let harmful:Vec<_>=foreign.into_iter().filter(|(position,_)|*position<ours.len()).collect();
        if !harmful.is_empty() {
            x.state.lock().unwrap().reset();
            let repairable=matches!(edit,Edit::Type(_))&&trigger!=TextInputTrigger::Enter&&harmful.iter().all(|(position,press)|*position>=selected&&press.char.is_some());
            let Some(held)=interleave(selected,&text,&harmful).filter(|_|repairable) else{result["failed"]=json!("替换过程中检测到其他输入，结果可能与输入顺序不同");return Ok(result)};
            let typed:String=harmful.iter().filter_map(|(_,press)|press.char).collect();
            let fixed=Self::select(x,desktop,guard,&held,held.chars().count(),false,0).await.map_err(partial)?;
            if fixed.text.as_deref()!=Some(held.as_str()){
                if align(&x.state.lock().unwrap().since(fixed.first),&fixed.sent).1.is_empty(){Self::unselect(desktop,guard,fixed.sent.iter().filter(|&&key|key==LEFT).count(),fixed.text.as_deref()).await.map_err(partial)?}
                result["failed"]=json!("替换过程中检测到其他输入，未能校验修正范围");return Ok(result);
            }
            let edit=Self::edit(x,&format!("{text}{typed}"));let mut ours=fixed.sent.clone();ours.extend(Self::apply(desktop,guard,&edit).await.map_err(partial)?);
            if x.until(Instant::now()+DELIVERY,|state|(align(&state.since(fixed.first),&ours).0==ours.len()).then_some(())).await.is_none(){return Err(partial(error(ErrorKind::Timeout,"修正按键未被 XWayland 确认送达")))}
            result["repaired"]=json!(true);return Ok(result);
        }
        {
            let mut state=x.state.lock().unwrap();
            let keep=state.typed.chars().count().saturating_sub(count);state.typed=state.typed.chars().take(keep).chain(text.chars()).collect();
        }
        let restore=format!("{}{}",expansion.keyword,if space{" "}else{""});
        let token=uuid::Uuid::new_v4().to_string();
        *self.undo.lock().await=Some(Undo{token:token.clone(),guard:guard.clone(),held:text,restore,after});
        result["undoToken"]=json!(token);Ok(result)
    }
    pub async fn undo(&self,session:&zbus::Connection,guard:Guard,token:&str)->Result<Option<Value>,Error>{
        let _editing=self.editing.lock().await;
        let mut slot=self.undo.lock().await;
        if !slot.as_ref().is_some_and(|entry|entry.token==token){return Ok(None)}
        let entry=slot.take().unwrap();drop(slot);
        if entry.guard!=guard{return Ok(Some(json!({"matched":false})))}
        let Some(x)=self.connection().await else{return Ok(Some(json!({"matched":false})))};
        x.sync().await.map_err(unmodified)?;
        // Any later key ends the undo window. Modifiers do not: Ctrl reaches
        // the client before Shell holds the Ctrl+Z that requested this undo.
        if x.state.lock().unwrap().since(entry.after).iter().any(|press|!press.modifier){return Ok(Some(json!({"matched":false})))}
        let desktop=Desktop::new(session.clone());
        crate::atspi::Adapter::guard(&desktop,&guard).await.map_err(unmodified)?;
        let _busy=Busy::new(&x);
        let result:Result<Value,Error>=async {
            let count=entry.held.chars().count();
            let selection=Self::select(&x,&desktop,&guard,&entry.held,count,false,0).await.map_err(partial)?;
            if selection.text.as_deref()!=Some(entry.held.as_str()){Self::unselect(&desktop,&guard,selection.sent.iter().filter(|&&key|key==LEFT).count(),selection.text.as_deref()).await.map_err(partial)?;return Ok(json!({"matched":false}))}
            let edit=Self::edit(&x,&entry.restore);let mut ours=selection.sent.clone();ours.extend(Self::apply(&desktop,&guard,&edit).await.map_err(partial)?);
            if x.until(Instant::now()+DELIVERY,|state|(align(&state.since(selection.first),&ours).0==ours.len()).then_some(())).await.is_none(){return Err(partial(error(ErrorKind::Timeout,"撤销按键未被 XWayland 确认送达")))}
            x.state.lock().unwrap().reset();
            Ok(json!({"matched":true,"adapter":"selection"}))
        }.await;
        result.map(Some)
    }
}
struct Selection {first:u64,exported:bool,text:Option<String>,sent:Vec<u32>}
enum Boundary {Separated,FieldStart,Word,Unknown}
/// Our keys must not enter the typed tail; a cancelled edit still resumes it.
struct Busy<'a>(&'a X);
impl<'a> Busy<'a> {fn new(x:&'a X)->Self{x.state.lock().unwrap().busy=true;Self(x)}}
impl Drop for Busy<'_> {fn drop(&mut self){self.0.state.lock().unwrap().busy=false}}

/// Selection results reach the runtime page; failures without an edit carry
/// the application so the page can offer an exclusion.
pub fn report(runtime:&crate::runtime::Runtime,guard:&Guard,value:&Value,success:&str){
    let (state,reason)=if value["unsupported"]==true{("unsupported",value["reason"].clone())}else if !value["failed"].is_null(){("failed",value["failed"].clone())}else if value["matched"]==true{(success,if value["repaired"]==true{json!("替换期间的其他输入已按输入顺序重新排列")}else{Value::Null})}else{return};
    runtime.event(json!({"event":"textExpansion","adapter":"selection","state":state,"ruleId":value["ruleId"],"reason":reason,"applicationId":guard.application_id,"undoToken":value["undoToken"]}));
}

#[cfg(test)]
mod tests {
    use super::*;
    fn press(sym:u32,char:Option<char>)->Press{Press{syms:[sym,sym],char,modifier:false}}
    #[test]
    fn alignment_separates_user_presses(){
        let presses=[press(LEFT,None),press(LEFT,None),press(0x78,Some('x')),Press{syms:[0x32,0x40],char:Some('2'),modifier:false},Press{syms:[SHIFT,SHIFT],char:None,modifier:true},press(0x30,Some('0'))];
        let (matched,foreign)=align(&presses,&[LEFT,LEFT,0x32,0x30]);
        assert_eq!(matched,4);assert_eq!(foreign.len(),1);assert_eq!(foreign[0].0,2);
        assert_eq!(align(&presses,&[LEFT,LEFT,0x40]).0,3);
        assert_eq!(interleave(2,"20",&foreign).unwrap(),"x20");
        assert_eq!(interleave(2,"20",&[(3,press(0x78,Some('x')))]).unwrap(),"2x0");
        assert!(interleave(2,"20",&[(2,press(0xff1b,None))]).is_none());
    }
    #[test]
    fn typed_tail_follows_keys_and_resets(){
        let mut state=State{keymap:Keymap{min:8,per:2,syms:vec![0;256]},..Default::default()};
        let set=|state:&mut State,code:u8,syms:[u32;2]|{let i=(code-8) as usize*2;state.keymap.syms[i]=syms[0];state.keymap.syms[i+1]=syms[1];};
        set(&mut state,38,[0x61,0x41]);set(&mut state,50,[SHIFT,SHIFT]);set(&mut state,22,[BACKSPACE,BACKSPACE]);set(&mut state,113,[LEFT,LEFT]);set(&mut state,37,[0xffe3,0xffe3]);
        for (code,pressed) in [(38,true),(50,true),(38,true),(50,false),(38,true)]{state.key(code,pressed)}
        assert_eq!(state.typed,"aAa");
        state.key(22,true);assert_eq!(state.typed,"aA");
        state.key(113,true);assert!(state.typed.is_empty()&&!state.known);
        state.key(38,true);state.key(37,true);state.key(38,true);assert!(state.typed.is_empty());
        state.key(37,false);state.busy=true;state.key(38,true);assert!(state.typed.is_empty());assert_eq!(state.presses.len(),state.total as usize);
    }
    #[test]
    fn caret_steps(){
        assert_eq!(graphemes("x中👍🏽"),3);assert_eq!(graphemes("e\u{301}a"),2);assert_eq!(graphemes("👨\u{200d}👩\u{200d}👧b"),2);
        assert_eq!(graphemes("🇯🇵🇨🇳"),2);assert_eq!(graphemes("abc"),3);assert_eq!(graphemes(""),0);
    }
    #[test]
    fn terminals_and_keywords(){
        assert!(terminal("XTerm")&&terminal("URxvt")&&!terminal("Tk")&&!terminal("Swing"));
        assert!("abc;中".chars().all(simple));assert!(!"e\u{301}".chars().all(simple));assert!(!"👍".chars().all(simple));
    }
}
