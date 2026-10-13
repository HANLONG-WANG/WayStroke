//! Mouse-only routing. Shape/length decisions use Shell coordinates in core.
use std::collections::BTreeSet;
use waystroke_protocol::{InputNotice,MouseEvent,StrokeDecision};
pub mod devices;
const SYN:u16=0;
const KEY:u16=1;
const REL:u16=2;
const RIGHT:u16=273;
#[derive(Debug,PartialEq)]
pub enum Effect { Forward(MouseEvent), Notify(InputNotice,f64) }
#[derive(Debug,PartialEq)]
enum Phase { Idle, Binding, Drawing, Deciding, Canceled }
#[derive(Debug)]
pub struct Router {
    phase:Phase, sequence:u32, held:BTreeSet<u16>, forwarded:BTreeSet<u16>,
    swallowed:BTreeSet<u16>, auxiliary:BTreeSet<u16>, buttons:Vec<MouseEvent>,
    queued:Vec<MouseEvent>, dx:i32, dy:i32,
}
impl Default for Router {
    fn default()->Self { Self{phase:Phase::Idle,sequence:0,held:BTreeSet::new(),forwarded:BTreeSet::new(),swallowed:BTreeSet::new(),auxiliary:BTreeSet::new(),buttons:vec![],queued:vec![],dx:0,dy:0} }
}
impl Router {
    fn forward(&mut self,e:MouseEvent,out:&mut Vec<Effect>) {
        if e.kind==KEY { if e.value==0 { self.forwarded.remove(&e.code); } else { self.forwarded.insert(e.code); } }
        out.push(Effect::Forward(e));
    }
    pub fn awaiting_start(&self)->bool { self.phase==Phase::Binding }
    pub fn awaiting_decision(&self)->bool { self.phase==Phase::Deciding }
    pub fn sequence(&self)->u32 { self.sequence }
    pub fn feed(&mut self,e:MouseEvent)->Result<Vec<Effect>,String> {
        if e.kind==SYN && e.code==3 { self.phase=Phase::Canceled;self.queued.clear();return Err("鼠标事件队列溢出，释放设备".into()); }
        if matches!(self.phase,Phase::Binding|Phase::Deciding) {
            self.queued.push(e);return Ok(vec![]);
        }
        let mut out=vec![];
        if e.kind==REL {
            if e.code==0 { self.dx+=e.value; } if e.code==1 { self.dy+=e.value; }
            self.forward(e,&mut out);return Ok(out);
        }
        if e.kind==SYN {
            if e.code==0 {
                if self.phase==Phase::Drawing && (self.dx!=0||self.dy!=0) {
                    out.push(Effect::Notify(InputNotice::Motion{sequence:self.sequence,dx:self.dx,dy:self.dy},e.monotonic_ms));
                }
                self.dx=0;self.dy=0;
            }
            self.forward(e,&mut out);return Ok(out);
        }
        if e.kind!=KEY || !(272..288).contains(&e.code) {
            // Preserve extra source capabilities without treating them as gestures.
            self.forward(e,&mut out);return Ok(out);
        }
        if e.value==2 { return Ok(out); }
        if self.swallowed.contains(&e.code) {
            if e.value==0 { self.swallowed.remove(&e.code);self.held.remove(&e.code); }
            return Ok(out);
        }
        let had_buttons=!self.held.is_empty();
        if e.value==0 { self.held.remove(&e.code); } else { self.held.insert(e.code); }
        if self.phase==Phase::Idle && e.code==RIGHT && e.value==1 && !had_buttons {
            self.sequence=self.sequence.checked_add(1).ok_or("手势序号已耗尽")?;
            self.phase=Phase::Binding;self.buttons=vec![e.clone()];self.auxiliary.clear();
            self.dx=0;self.dy=0;
            self.forward(MouseEvent{kind:SYN,code:0,value:0,monotonic_ms:0.},&mut out);
            out.push(Effect::Notify(InputNotice::Begin{sequence:self.sequence},e.monotonic_ms));
            return Ok(out);
        }
        if matches!(self.phase,Phase::Drawing|Phase::Canceled) {
            self.buttons.push(e.clone());
            if e.code!=RIGHT && e.value==1 && self.auxiliary.insert(e.code) && self.phase==Phase::Drawing {
                out.push(Effect::Notify(InputNotice::Auxiliary{sequence:self.sequence,button:e.code},e.monotonic_ms));
            }
            if e.code==RIGHT && e.value==0 {
                if self.phase==Phase::Canceled {
                    self.swallowed.extend(self.held.iter());self.buttons.clear();self.phase=Phase::Idle;
                } else {
                    // Flush the last physical frame before the Shell end barrier.
                    if self.dx!=0||self.dy!=0 {out.push(Effect::Notify(InputNotice::Motion{sequence:self.sequence,dx:self.dx,dy:self.dy},e.monotonic_ms));}
                    self.dx=0;self.dy=0;self.forward(MouseEvent{kind:SYN,code:0,value:0,monotonic_ms:0.},&mut out);
                    self.phase=Phase::Deciding;
                    out.push(Effect::Notify(InputNotice::Finish{sequence:self.sequence,auxiliary_buttons:self.auxiliary.iter().copied().collect()},e.monotonic_ms));
                }
            }
        } else { self.forward(e,&mut out); }
        Ok(out)
    }
    pub fn bound(&mut self,sequence:u32)->Result<Vec<Effect>,String> {
        if self.phase!=Phase::Binding || sequence!=self.sequence { return Err("起点确认已过期".into()); }
        self.phase=Phase::Drawing;self.drain()
    }
    pub fn bypass(&mut self,sequence:u32)->Result<Vec<Effect>,String> {
        if self.phase!=Phase::Binding||sequence!=self.sequence {return Err("起点确认已过期".into());}
        let mut out=vec![];for event in std::mem::take(&mut self.buttons){self.forward(event,&mut out);}
        self.forward(MouseEvent{kind:SYN,code:0,value:0,monotonic_ms:0.},&mut out);self.phase=Phase::Idle;out.extend(self.drain()?);Ok(out)
    }
    pub fn decide(&mut self,sequence:u32,decision:StrokeDecision)->Result<Vec<Effect>,String> {
        if self.phase!=Phase::Deciding || sequence!=self.sequence { return Err("手势结果已过期".into()); }
        let mut out=vec![];
        if decision==StrokeDecision::Click {
            for e in std::mem::take(&mut self.buttons) { self.forward(e,&mut out);self.forward(MouseEvent{kind:SYN,code:0,value:0,monotonic_ms:0.},&mut out); }
        } else { self.buttons.clear();self.swallowed.extend(self.held.iter()); }
        self.phase=Phase::Idle;out.extend(self.drain()?);Ok(out)
    }
    pub fn cancel(&mut self,sequence:u32)->Result<Vec<Effect>,String> {
        if sequence!=self.sequence || self.phase==Phase::Idle { return Err("没有对应的活动手势".into()); }
        if self.phase==Phase::Deciding { return self.decide(sequence,StrokeDecision::Consume); }
        self.phase=Phase::Canceled;self.drain()
    }
    fn drain(&mut self)->Result<Vec<Effect>,String> {
        let events=std::mem::take(&mut self.queued);let mut out=vec![];
        for e in events { out.extend(self.feed(e)?); } Ok(out)
    }
    pub fn recover_completed_click(&mut self)->Vec<Effect> {
        // A lost start handshake may still contain a complete stationary click.
        // Any queued motion leaves the decision to core; never guess its length.
        if self.phase==Phase::Binding
            && self.queued.iter().any(|e|e.kind==KEY&&e.code==RIGHT&&e.value==0)
            && !self.queued.iter().any(|e|e.kind==REL&&e.code<=1&&e.value!=0) {
            return self.bypass(self.sequence).expect("binding state checked");
        }
        vec![]
    }
    pub fn release(&mut self)->Vec<Effect> {
        let mut out=vec![];
        for code in self.forwarded.iter().copied().collect::<Vec<_>>() { self.forward(MouseEvent{kind:KEY,code,value:0,monotonic_ms:0.},&mut out); }
        self.forward(MouseEvent{kind:SYN,code:0,value:0,monotonic_ms:0.},&mut out);
        *self=Self::default();out
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn e(kind:u16,code:u16,value:i32)->MouseEvent { MouseEvent{kind,code,value,monotonic_ms:0.} }
    #[test]
    fn binding_freezes_then_click_replays_and_stroke_consumes() {
        let mut r=Router::default();let start=r.feed(e(KEY,RIGHT,1)).unwrap();assert!(matches!(start.last(),Some(Effect::Notify(InputNotice::Begin{sequence:1},_))));
        assert!(r.feed(e(REL,0,20)).unwrap().is_empty());assert!(r.feed(e(KEY,RIGHT,0)).unwrap().is_empty());
        let bound=r.bound(1).unwrap();assert!(bound.iter().any(|x|matches!(x,Effect::Forward(MouseEvent{kind:REL,..}))));
        let replay=r.decide(1,StrokeDecision::Click).unwrap();assert!(replay.contains(&Effect::Forward(e(KEY,RIGHT,1))));assert!(replay.contains(&Effect::Forward(e(KEY,RIGHT,0))));
        r.feed(e(KEY,RIGHT,1)).unwrap();r.bound(2).unwrap();r.feed(e(KEY,275,1)).unwrap();r.feed(e(KEY,RIGHT,0)).unwrap();
        assert!(!r.decide(2,StrokeDecision::Consume).unwrap().iter().any(|x|matches!(x,Effect::Forward(MouseEvent{kind:KEY,..}))));assert!(r.feed(e(KEY,275,0)).unwrap().is_empty());
    }
    #[test]
    fn auxiliary_pressed_after_drawing_is_noticed_and_retained_until_finish() {
        let mut r=Router::default();r.feed(e(KEY,RIGHT,1)).unwrap();r.bound(1).unwrap();r.feed(e(REL,0,120)).unwrap();
        let pressed=r.feed(e(KEY,272,1)).unwrap();
        assert!(pressed.iter().any(|x|matches!(x,Effect::Notify(InputNotice::Auxiliary{sequence:1,button:272},_))));
        r.feed(e(KEY,272,0)).unwrap();
        let finished=r.feed(e(KEY,RIGHT,0)).unwrap();
        assert!(finished.iter().any(|x|matches!(x,Effect::Notify(InputNotice::Finish{sequence:1,auxiliary_buttons},_) if auxiliary_buttons==&vec![272])));
        assert!(!r.decide(1,StrokeDecision::Consume).unwrap().iter().any(|x|matches!(x,Effect::Forward(MouseEvent{kind:KEY,..}))));
    }
    #[test]
    fn stationary_completed_click_survives_failed_binding_but_overflow_does_not_replay() {
        let mut r=Router::default();r.feed(e(KEY,RIGHT,1)).unwrap();r.feed(e(KEY,RIGHT,0)).unwrap();
        assert!(r.recover_completed_click().contains(&Effect::Forward(e(KEY,RIGHT,0))));
        r.feed(e(KEY,RIGHT,1)).unwrap();r.feed(e(KEY,RIGHT,0)).unwrap();assert!(r.feed(e(SYN,3,0)).is_err());assert!(r.recover_completed_click().is_empty());
    }
    #[test]
    fn auxiliary_alone_passes_and_cancel_never_replays_menu() {
        let mut r=Router::default();assert_eq!(r.feed(e(KEY,275,1)).unwrap(),vec![Effect::Forward(e(KEY,275,1))]);r.feed(e(KEY,275,0)).unwrap();
        r.feed(e(KEY,RIGHT,1)).unwrap();r.cancel(1).unwrap();assert!(r.feed(e(KEY,RIGHT,0)).unwrap().is_empty());
        assert!(r.feed(e(SYN,3,0)).is_err());r.release();
        r.feed(e(KEY,272,1)).unwrap();assert!(r.release().contains(&Effect::Forward(e(KEY,272,0))));
    }
}
