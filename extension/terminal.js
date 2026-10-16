import Clutter from 'gi://Clutter';

// VTE receives a single ordered commit containing DEL and replacement bytes.
// No shell plugin, password detection, history or persistent keystroke log.
export class TerminalAdapter {
    constructor(bridge){
        this.bridge=bridge;this.token='';this.limit=1;this.uncertain=false;this.owners=new Set();
        this.selection=global.display.get_selection();
        this.selectionSignal=this.selection.connect('owner-changed',(_selection,_type,owner)=>{if(owner){if(this.watch)this.native.watch_add_source(this.watch,owner);else this.owners.add(owner)}});
        import('gi://WayStrokeClipboard?version=1.0').then(module=>{
            if(!bridge.alive)return;
            this.native=module.default;this.watch=this.native.watch_new();
            this.watchSignal=this.watch.connect('requested',()=>{if(this.active()){this.bridge.generation++;this.bridge.undo=null;this.clear(true)}});
            for(const owner of this.owners)this.native.watch_add_source(this.watch,owner);this.owners.clear();
            bridge.updateGrabs();
        }).catch(error=>bridge.failure(error,'terminal'));
    }
    disable(){
        this.selection.disconnect(this.selectionSignal);this.owners.clear();
        if(this.watch){this.watch.disconnect(this.watchSignal);this.native.watch_stop(this.watch);this.watch=null}this.clear(true);
    }
    configure(config){this.enabled=config.settings.terminalTextEnabled;this.limit=Math.max(1,...config.snippets.map(rule=>[...rule.key].length))+1;this.clear()}
    clear(uncertain=false){this.token='';this.uncertain=uncertain;this.commitContext=null}
    focused(){return !!this.bridge.im.currentFocus&&this.bridge.im.content_purpose===Clutter.InputContentPurpose.TERMINAL}
    active(){
        const window=global.display.focus_window;
        return this.focused()&&!!this.watch&&!!this.bridge.im._context&&this.enabled&&this.bridge.enabled&&!this.bridge.extension.locked()&&!!window&&!this.bridge.excludedApplications?.has(this.bridge.extension.windowInfo(window).applicationId);
    }
    snapshot(){
        if(!this.active()||this.bridge.composing())return null;
        const window=global.display.focus_window;if(!window)return null;
        const applicationId=this.bridge.extension.windowInfo(window).applicationId;
        if(this.bridge.excludedApplications?.has(applicationId))return null;
        const cursor=[...this.token].length;
        return {adapter:'terminal',focus:this.bridge.im.currentFocus,window,text:this.token,cursor,anchor:cursor,generation:this.bridge.generation,applicationId,uncertain:this.uncertain};
    }
    append(text){this.token=[...this.token+text].slice(-this.limit).join('')}
    committed(text){
        if(!this.active()||this.bridge.applying)return;
        this.bridge.undo=null;this.append(text);
        const origin={focus:this.bridge.im.currentFocus,window:global.display.focus_window,generation:this.bridge.generation,token:this.token};
        this.commitContext=origin;
        this.bridge.later(0,()=>this.resumeCommitted());
        this.bridge.later(500,()=>{if(this.commitContext===origin)this.commitContext=null});
    }
    resumeCommitted(){
        const origin=this.commitContext;if(!origin||this.bridge.composing())return;
        this.commitContext=null;
        const snapshot=this.snapshot();
        if(!snapshot||origin.focus!==snapshot.focus||origin.window!==snapshot.window||origin.generation!==snapshot.generation||origin.token!==snapshot.text)return;
        this.bridge.run(()=>this.bridge.expand(snapshot,'commit')).catch(error=>this.bridge.failure(error));
    }
    key(event,handled){
        if(!this.focused())return false;
        const key=event.get_key_symbol(),state=event.get_state();
        if([Clutter.KEY_Shift_L,Clutter.KEY_Shift_R,Clutter.KEY_Control_L,Clutter.KEY_Control_R].includes(key))return false;
        if(state&(Clutter.ModifierType.CONTROL_MASK|Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK)){
            // Ctrl+U is a line kill in the supported canonical/Readline modes.
            this.clear(!(state&Clutter.ModifierType.CONTROL_MASK&&key===Clutter.KEY_u));return false;
        }
        if(handled){
            // IBus can emit CommitText before reporting the same handled press.
            // Carry that one post-IME generation forward; focus/context resets
            // still discard the origin, and later unrelated presses do not.
            const origin=this.commitContext;
            if(origin&&origin.generation+1===this.bridge.generation&&origin.focus===this.bridge.im.currentFocus&&origin.window===global.display.focus_window)origin.generation=this.bridge.generation;
            this.bridge.later(0,()=>this.resumeCommitted());return false;
        }
        if(this.bridge.composing())return false;
        const snapshot=this.snapshot();if(!snapshot)return false;
        if(key===Clutter.KEY_space||key===Clutter.KEY_Return){
            this.bridge.candidates.set(event.get_time(),{snapshot});
            this.bridge.run(()=>this.bridge.confirm({key,code:event.get_key_code(),trigger:key===Clutter.KEY_space?'space':'enter'},event.get_time())).catch(error=>this.bridge.failure(error));
            return true;
        }
        if(key===Clutter.KEY_BackSpace){this.token=[...this.token].slice(0,-1).join('');return false}
        const codepoint=Clutter.keysym_to_unicode(key);
        if(codepoint>=32&&codepoint!==127){
            const text=String.fromCodePoint(codepoint);
            this.append(text);this.bridge.originalCommit.call(this.bridge.im,text);
            const next=this.snapshot();if(next)this.bridge.run(()=>this.bridge.expand(next,'commit')).catch(error=>this.bridge.failure(error));
            return true;
        }
        if(![Clutter.KEY_Shift_L,Clutter.KEY_Shift_R,Clutter.KEY_Control_L,Clutter.KEY_Control_R].includes(key))this.clear(true);
        return false;
    }
    apply(snapshot,result){
        const start=snapshot.cursor-result.deleteChars;
        const confirmation=result.preserve?result.confirmation:'';
        this.bridge.applying=true;
        try{this.bridge.originalCommit.call(this.bridge.im,'\x7f'.repeat(result.deleteChars)+result.replacement+confirmation)}finally{this.bridge.applying=false}
        this.token=[...snapshot.text].slice(0,start).join('')+result.replacement+confirmation;
        // A newline submits a line; it cannot be undone as local editing.
        this.bridge.undo=/[\r\n]/.test(result.replacement+confirmation)?null:{...snapshot,text:this.token,cursor:[...this.token].length,anchor:[...this.token].length,start,before:snapshot.text+confirmation,beforeCursor:snapshot.cursor+[...confirmation].length,ruleId:result.ruleId};
        if(/[\r\n]/.test(this.token))this.clear();else if(!this.bridge.undo)this.token=[...this.token].slice(-this.limit).join('');
        this.bridge.extension.changed({event:'textExpansion',adapter:'terminal',state:'submitted',ruleId:result.ruleId,reason:'已提交至终端；canonical/Readline/getpass 支持，raw/TUI 编辑结果无法确认'});
        return {matched:true,preserve:result.preserve,confirmationHandled:true};
    }
    confirmUnmatched(grab){
        const text=grab.trigger==='enter'?'\n':' ';
        this.bridge.originalCommit.call(this.bridge.im,text);
        if(grab.trigger==='enter')this.clear();
        else if(this.bridge.immediateCharacters.includes(text))this.committed(text);
        else this.append(text);
    }
    undo(record,actual){
        this.bridge.undo=null;
        const count=actual.cursor-record.start,replacement=[...record.before].slice(record.start,record.beforeCursor).join('');
        this.bridge.originalCommit.call(this.bridge.im,'\x7f'.repeat(count)+replacement);
        this.token=record.before;
        this.bridge.extension.changed({event:'textExpansion',adapter:'terminal',state:'undoSubmitted',ruleId:record.ruleId,reason:'仅恢复紧邻输入；终端不提供文档级撤销或 raw/TUI 编辑确认'});
        return true;
    }
}
