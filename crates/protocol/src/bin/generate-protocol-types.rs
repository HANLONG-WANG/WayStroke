use std::fs;
use ts_rs::TS;
use waystroke_protocol::*;
fn main() {
    let types=[Snapshot::decl(),Commit::decl(),ErrorKind::decl(),Error::decl(),Reply::<Snapshot>::decl(),Status::decl()];
    fs::write("apps/desktop/src/generated/protocol.ts",format!("// Generated from waystroke-protocol; do not edit.\nimport type {{Config,ValidationError}} from './model';\nexport const PROTOCOL_VERSION = {};\n{}\n",PROTOCOL_VERSION,types.into_iter().map(|t|format!("export {t}")).collect::<Vec<_>>().join("\n"))).unwrap();
}
