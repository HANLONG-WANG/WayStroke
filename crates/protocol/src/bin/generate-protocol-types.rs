use std::fs;
use ts_rs::TS;
use waystroke_protocol::*;
fn main() {
    let types=[ConfigurationRequest::decl(),ImportMode::decl(),ConfigCounts::decl(),ImportPreview::decl(),BackupSummary::decl(),Snapshot::decl(),Commit::decl(),ErrorKind::decl(),Error::decl(),Reply::<Snapshot>::decl(),Status::decl(),ActionAvailability::decl(),ActionCapability::decl(),MouseDevice::decl(),MouseEvent::decl(),StrokeDecision::decl(),InputRequest::decl(),InputNotice::decl(),InputCommand::decl(),InputResult::decl(),BarrierStage::decl(),InputPacket::decl(),RecognitionRequest::decl(),RecognitionOutcome::decl(),Candidate::decl(),RecognitionResult::decl(),GestureTiming::decl(),RuntimeInfo::decl(),TextStatus::decl(),TextResult::decl(),TextMatchRequest::decl(),TextInputTrigger::decl(),TextExpansion::decl()];
    fs::write("apps/desktop/src/generated/protocol.ts",format!("// Generated from waystroke-protocol; do not edit.\nimport type {{Config,ValidationError,StartContext,Execution}} from './model';\nexport const PROTOCOL_VERSION = {};\n{}\n",PROTOCOL_VERSION,types.into_iter().map(|t|format!("export {t}")).collect::<Vec<_>>().join("\n"))).unwrap();
}
