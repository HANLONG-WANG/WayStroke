# 修饰确认键与微信兼容替换回归

GNOME Shell 50.5 / Mutter 50.6，Fedora 44。除 `wechat-session-selection.json` 外，全部在私有 D-Bus、XDG 和 mutter-devkit 显示中执行。

| 证据 | 覆盖 |
| --- | --- |
| `native-modifiers.json` | 普通 Wayland 输入：Shift、AltGr、Ctrl + Enter/Space 在关键词匹配和不匹配时都不进入确认，客户端收到原修饰（Shift=1、Ctrl=4；GTK4 不公开 Mod5，AltGr 以 Shell 实际状态核对）；普通 Enter 匹配替换、不匹配原样；Super+Space 切换输入源。 |
| `terminal-modifiers.json` | 声明 TERMINAL 用途的字段经 TerminalAdapter：同样 6 个修饰组合原样送达。 |
| `selection.json` | XWayland Shift+Enter/Space 透传；Tk、Swing 全部既有用例；复制选区夹具（窗口类 WeChat）空格替换，**一次替换只有两次剪贴板所有者变化（复制一次、恢复一次）**，撤销，行首 Enter，文本/HTML/二进制格式逐项恢复。该次运行在行首 Enter 之后因 devkit 停止出帧中断（见下）。 |
| `selection-copy-rest.json` | 复制选区夹具的其余用例：Unicode 经粘贴替换、前一字符为字母时不替换、旧剪贴板即使等于关键词也不能冒充新复制、三次无复制后报告“兼容替换不可用”，每次格式全部恢复。 |
| `selection-terminals.json` | xterm 按终端名单跳过；不导出选区的普通窗口恰好收到三对 Shift+方向键后停用。 |
| `wechat-session-selection.json` | 用户同意后在主桌面只读观察 XFixes 选区所有者变化（不读内容、不发输入）。微信聊天框中键盘选择与鼠标拖选都不设置 PRIMARY，只有 Ctrl+C 设置 CLIPBOARD。 |
| `wechat-probe.json` | 隔离 HOME 启动 `/opt/wechat/wechat`：XWayland、WM_CLASS=wechat；未登录界面只有二维码。 |

重跑（需要 release core、原生组件、Tk/PySide6/JDK/xterm）：

```sh
python3 scripts/check-gnome.py --devkit --multi-monitor --release --phase-d-text --modifiers
python3 scripts/check-gnome.py --devkit --release --phase-d-text --modifiers --terminal-modifiers
python3 scripts/check-gnome.py --devkit --release --phase-d-atspi --selection
```

`source.json` 记录归档时的源码与二进制哈希。

说明：

- 2026-10-22 晚间启用 XWayland 的 devkit 多次在随机位置停止出帧（Shell 输入帧不到达，`shell.log` 有 “Frame has assigned frame counter but no frame drawn time” 与 pixman 无效矩形），同时段已提交的 HEAD 两次复现同样停顿，未启用 XWayland 的 `--phase-d-text` 通过。因此 `selection.json` 中断后，用只保留剩余用例的临时副本分段补跑，生产扩展与 core 未改动；没有把中断的运行标作通过。锁屏或显示器关闭时 devkit 同样无法出帧。
- 为 devkit 整体设置 `__EGL_VENDOR_LIBRARY_FILENAMES=.../50_mesa.json` 会让 devkit 里的 Shell 因 NVIDIA 设备没有 EGL 显示而无法启动，不要用于 `check-gnome.py`。
- 复制读回只用于窗口类 wechat/weixin，不对其他不导出选区的客户端发送 Ctrl+C。每次替换的那一次复制会被剪贴板管理器（如 CopyQ）记入历史；随后恢复的原剪贴板也可能再次被记录。
- 未直接运行 Claude Code 宿主或登录后的微信做最终替换验收；已覆盖它们使用的原生、TERMINAL、XWayland 路径，以及微信实际的选区行为。
