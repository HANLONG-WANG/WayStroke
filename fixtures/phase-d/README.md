# 阶段 D 验收证据

阶段 D 已完成，最终需求核对见 [实施计划](../../docs/implementation-plan.md)。扩展检查全部在私有 mutter-devkit / GNOME 50.5 中进行，未测试、部署或修改主桌面。输入只使用固定夹具，devkit 向外层桌面的剪贴板转发已关闭，鼠标未接管。

| 结果 | 实际覆盖 |
| --- | --- |
| [native-gtk.json](native-gtk.json) | 原生 GTK 的确认、立即、确认吞掉/保留、紧邻撤销、导航失效、密码保护、排除/开关、生成提交及虚拟按键抑制；GtkTextView 中文多行；同窗字段切换时取消等待中的匹配；Rime 真实提交、中文确认/立即、自身键盘经 IBus 提交的抑制；core/IBus 停止恢复及真实锁屏/解锁。 |
| [atspi-xwayland.json](atspi-xwayland.json) | GTK/XWayland 的 PID/窗口/编辑节点验证；确认与立即；UTF-8/Unicode 光标；撤销/导航失效及状态同步；密码/旧窗口保护；生成/粘贴抑制；Shift/Caps Lock 和保持按下的键；GtkTextView 中文多行及撤销；同窗竞态；Rime 组合、确认和立即；注册服务重启后同一应用恢复。 |
| [terminal-vte.json](terminal-vte.json) | 24 项实际 Ptyxis/VTE 检查：canonical、Readline、getpass、四种触发代表分支、确认吞掉、紧邻撤销、导航/焦点/前边界、独立开关/排除、自身文本与按键、中文 IME 确认和立即、空格结尾关键词、中键主选区与真正 GTK 外部选区粘贴，以及 raw 字节限制。 |
| [firefox-native.json](firefox-native.json) / [electron-native.json](electron-native.json) | 实际浏览器中文多行、确认保留、紧邻撤销、立即、密码字段、同窗 contenteditable、Rime 组合保护/消费确认/中文确认与立即。 |
| [ui-native.json](ui-native.json) | 正式 Tauri/WebKitGTK 界面的页内共享匹配与多行撤销；现有规则编辑后 ID/触发/大小写/确认选项持久保存，并实际匹配；真实 GTK 的能力与最近结果、密码/停用、锁屏/解锁状态；[用户帮助截图](text-help.png)。 |

重跑命令（先构建 core、桌面窗口及原生组件，并具备 devkit、Rime、浏览器和 UI 驱动）：

```sh
python3 scripts/check-gnome.py --devkit --phase-d-text --multiline --focus-race --ime --lifecycle
python3 scripts/check-gnome.py --devkit --phase-d-atspi --caps --multiline --focus-race --ime --lifecycle
python3 scripts/check-gnome.py --devkit --phase-d-terminal
python3 scripts/check-gnome.py --devkit --phase-d-browser
python3 scripts/check-gnome.py --devkit --phase-d-browser --electron
python3 scripts/check-ui.py --devkit --phase-d
```

共享匹配器的前边界、大小写、应用专属跨触发覆盖、停用回退、四种触发、多行与输入策略由 `cargo test -p waystroke-core -p waystroke-model --offline` 验证（6 + 4 项通过）。原生组件构建、MIME 原样读回、传输观察器停用，前端类型检查、Vite 构建、桌面 custom-protocol 构建及 diff 检查通过。

`*-source.json` 记录各分支命令、临时目录和实际加载的扩展副本哈希。`sourceSha256AtArchive` / `binarySha256AtArchive` 是最终工作树与构建产物的归档哈希，不冒充每次旧运行的精确二进制。夹具仅在私有副本加入诊断与一次 RPC 的调度门控，实际匹配、字段切换、插入和结果均由正式实现和真正客户端完成。生命周期文件保留对应完整分支结果。

支持边界：Firefox/GTK 多行可能只回报当前段落；完整范围不可确认时不进行受控撤销，交还应用原生撤销，并明确报告范围受限。终端普通及密码输入均允许，开关停用整个终端路径；含换行/已提交行不能紧邻撤销。raw/TUI 只能报告编辑字节已提交，不能宣称文档已修改；不把 VTE 结果推广成所有终端程序保证。导航、快捷键、粘贴和焦点变化清除短期上下文，未知前边界不按空文档猜测。

`terminal-paste-pending.json` 与 DeviceEventController XML 是历史实验记录，不是当前未完成门槛；中键粘贴已由最新两种真实 source 的通过结果替代。无效的客户端 Clutter 鼠标过滤器、DeviceEventController 键盘监听以及 XTEST/XSendEvent 实验均未保留为支持路径。最终 XWayland 重放使用固定 GNOME 50.5 的 Clutter 导出事件构造器，保留原键码和修饰状态，并标记自身来源。
