# XWayland 兼容替换验收证据

适用于没有 AT-SPI 文本接口的 XWayland 程序：选区校验替换（实现见 `crates/core/src/xselection.rs`）。全部检查在私有 mutter-devkit / GNOME 50.5 中进行，只使用固定夹具，没有改动主桌面。按键来自探针扩展的虚拟键盘，代替用户的物理键盘；替换按键来自 WayStroke 扩展自身的虚拟键盘。

| 结果 | 实际覆盖 |
| --- | --- |
| [selection-xwayland.json](selection-xwayland.json) | Tk：空格确认、紧邻撤销、行首 Enter（activate 收到 2003）、中文与 emoji 经粘贴替换、前边界为字母时不替换、前边界为符号时替换、密码字段不编辑、立即规则、按应用停用兼容替换；输入尾部与实际文字不一致时还原选区，包括光标前为 `👍🏽` 及选区在字段开头截短的情况。Swing：空格确认、撤销、粘贴、密码字段。xterm 按终端名单跳过，程序只收到原输入。不导出选区的非终端窗口每次触发只多收到一对 Shift+方向键，第三次后停用并报告“兼容替换不可用”。空格后 0–80ms 内继续输入的结果，以及不匹配时 Space 的等待时长。 |
| [ui-selection.json](ui-selection.json) | 正式 Tauri/WebKitGTK 界面：排除行的“停用兼容替换”选项与默认值；运行状态页根据真实的“兼容替换不可用”结果显示按钮，按钮注明目标应用，点击后写入该应用的兼容替换排除。截图：[设置](ui-selection-settings.png)、[运行状态](ui-selection-runtime.png)。 |

重跑命令（先构建 release core、桌面窗口及原生组件，需要 PySide6/Tk、JDK、xterm）：

```sh
python3 scripts/check-gnome.py --devkit --release --phase-d-atspi --selection
python3 scripts/check-ui.py --devkit --release --selection-ui
```

`source.json` 记录命令、临时目录以及归档时的源码与二进制哈希。

结果说明：

- 空格后的下一个键：0ms 时它先于被扣住的 Space 到达程序，关键词未替换，得到 `hi abcx `（现有确认键路径同样如此，不会丢字）；10–80ms 时替换先完成，得到 `hi 2003 x`。按到达顺序修正替换期间插入按键的逻辑由 `cargo test -p waystroke-core xselection` 覆盖，本轮端到端运行中没有出现需要修正的时序。
- 不匹配时 Space 的等待为 6–33ms（AT-SPI 查询与 XWayland 同步）；在这段时间内按下的键会排到 Space 之前。
- 程序在校验完成前收到用户按键时，关键词可能已被覆盖且内容未经校验，此时不编辑，只报告失败。
- 还原按读回选区的实际光标步数进行：选区在字段开头截短时不多按 Shift+→，避免选中原光标之后的文字。Tk 无法跨越光标前的多码点字符缩短选区，此时追加一次 → 与 ←：中间位置回到原光标（`x👍🏽 Zyz`）；在文本末尾光标会提前一个位置（`x中 Z👍🏽`），但不丢失字符。
- 归档的 check-gnome 运行加载的扩展含四行临时 `console.log`（不改变行为），且早于测试在用例之间等待 Shell 队列清空的加固；见 `source.json`。之后在本机启用 XWayland 的 devkit 运行多次停在共用的准备步骤（隐藏概览超时）或等待 Shell 输入帧，未启用 XWayland 的 `--phase-d-text` 同时通过。

2026-10-22 的修饰确认键与复制选区修复回归另见 [text-compatibility](../text-compatibility/README.md)：新增微信类复制选区夹具、所有剪贴板数据格式恢复及 XWayland Shift 确认键透传；本目录保留此前验收与 UI 的历史证据。
