//! Discover relative mice before opening any input node; never capture keyboards.
use evdev::{Device,KeyCode,RelativeAxisCode,AbsoluteAxisCode};
use std::{io,path::Path,process::Command};
use waystroke_protocol::MouseDevice;
pub const VIRTUAL_PREFIX:&str="WayStroke Virtual";
pub fn eligible(device:&Device)->bool {
    if device.name().unwrap_or("").starts_with(VIRTUAL_PREFIX) || device.name().unwrap_or("").starts_with("WayStroke Input Probe") { return false; }
    let Some(keys)=device.supported_keys() else { return false; };
    let Some(rel)=device.supported_relative_axes() else { return false; };
    if !keys.contains(KeyCode::BTN_LEFT)||!keys.contains(KeyCode::BTN_RIGHT)||!rel.contains(RelativeAxisCode::REL_X)||!rel.contains(RelativeAxisCode::REL_Y) { return false; }
    !device.supported_absolute_axes().is_some_and(|axes|[AbsoluteAxisCode::ABS_X,AbsoluteAxisCode::ABS_Y,AbsoluteAxisCode::ABS_MT_SLOT,AbsoluteAxisCode::ABS_MT_POSITION_X,AbsoluteAxisCode::ABS_MT_POSITION_Y].iter().any(|axis|axes.contains(*axis)))
}
pub fn enumerate()->io::Result<Vec<MouseDevice>> {
    let mut found=vec![];
    for entry in std::fs::read_dir("/sys/class/input")? {
        let entry=entry?;let name=entry.file_name();let Some(name)=name.to_str() else { continue; };
        if !name.starts_with("event") { continue; }
        let Ok(axes)=std::fs::read_to_string(entry.path().join("device/capabilities/rel")) else { continue; };
        if !axes.split_whitespace().last().and_then(|s|u64::from_str_radix(s,16).ok()).is_some_and(|mask|mask&3==3) { continue; }
        let path=Path::new("/dev/input").join(name);let device=Device::open(&path)?;
        if !eligible(&device) { continue; }
        let output=Command::new("udevadm").args(["info","--query=property","--name"]).arg(&path).output()?;
        if !output.status.success() { return Err(io::Error::other("无法读取鼠标稳定身份")); }
        let props=String::from_utf8_lossy(&output.stdout);let property=|key:&str|props.lines().find_map(|line|line.strip_prefix(&format!("{key}=")));
        let location=property("ID_PATH").or(device.physical_path());let identity=property("ID_SERIAL").filter(|s|!s.is_empty()).or(location).ok_or_else(||io::Error::other("鼠标没有稳定物理身份"))?;
        let interface=property("ID_USB_INTERFACE_NUM").unwrap_or("0");
        // phys separates the relative-mouse interface on composite receivers.
        let id=format!("mouse:{identity}:{interface}:{}",device.physical_path().unwrap_or(""));
        found.push(MouseDevice{id,name:device.name().unwrap_or("鼠标").into(),path:path.to_string_lossy().into_owned(),physical_path:location.map(str::to_owned)});
    }
    found.sort_by(|a,b|a.id.cmp(&b.id));Ok(found)
}
