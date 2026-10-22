# GNOME 50.5 开发前技术验证

目标：用户当前 Fedora 44 Workstation，GNOME Shell / Mutter 50.5，Wayland。仅适配此版本，不新增跨版本兼容工作。实测日期：2026-10-13。

## 当前状态

核心鼠标输入服务已取得用户 G304 实测证据，起点绑定协议的隔离时序检查及真实鼠标跨窗绑定检查均通过。最新设备编号为 event7。以下早期章节保留验证过程，不代表最新待办。

代表性应用检查已有结果：Firefox、Electron/Code、组合快捷键与两种键盘布局，以及 XWayland 窗口接口。第三阶段已验证 XWayland GTK 的 AT-SPI 编辑/密码角色、自动空格替换，以及 GNOME accelerator 的 Enter 保留和重放路径。用户允许终端密码也替换后，第四阶段已验证无需 Shell 集成的普通/Readline/密码输入、空格/Enter 和 Rime 路径。原始输入程序不解释删除控制字符，仍不能宣称任意终端程序均可正确替换，具体边界见第四阶段。第五阶段验证了缺少 AT-SPI 文本接口的 XWayland 程序的回退前提（选区校验替换），随后已实现为默认启用、可按应用停用的兼容替换，见该节末尾。

## 第一轮结论

窗口定位、窗口操作与输入发送存在实测可行路径；GTK 文本输入协议支持文本替换、中文提交与 Rime 组合状态识别。鼠标手势尚未取得完整可用的输入拦截方案。不能开始正式实现后再把这一问题掩盖为“待优化”。

**纯 GNOME 扩展监听 Stage 的 `captured-event` 无法满足普通应用内按住右键绘制的需求。** 这是本轮最重要的限制。建议下一轮验证受控的鼠标输入服务与扩展协作；此为推荐路线，不是已经验证通过或已安装的方案。

## 实测环境与方法

- 安装包：gnome-shell 50.5-1.fc44、mutter 50.5-1.fc44、gjs 1.88.1、GTK 4.22.5、IBus 1.5.34。
- 当前会话环境变量报告 GNOME / Wayland；主桌面 D-Bus `ShellVersion` 返回 50.5。
- 测试运行一个单独的 GNOME Shell 50.5：私有 D-Bus、临时 XDG 目录、headless Wayland、1280×800 虚拟屏幕、软件渲染、禁用测试实例 XWayland。
- 扩展仅放在临时目录，限制只能在测试运行器创建的会话中启用。主桌面未安装该扩展、未开启 unsafe-mode、未变更输入设备权限。
- 创建两个专用 GTK 窗口，测试文本都是固定样本。没有采集用户真实键盘输入。
- 手势事件通过 Clutter 虚拟设备生成，尚未使用真实鼠标进行 evdev 拦截。
- 关闭测试实例的热角，确保鼠标测试在普通窗口模式进行。初期测试受到概览模式影响，其结果未作为最终结论；最后一轮确认 `overview=false`、真实应用计数和 Shell 计数。

可复跑的代码位于 `probes/gnome50/`；最终原始结果与检查位于 `results-50.5.json`。

## 第一阶段验证结果

| 能力 | 状态 | 实测证据与限制 |
| --- | --- | --- |
| 按坐标定位未聚焦窗口 | 通过（测试窗口） | 焦点在 Probe B，在 Probe A 坐标拾取到其 Wayland surface actor，沿父级取得 Meta.Window；返回 A，未误用焦点 B。弹出菜单、窗口阴影、多屏缩放和穿透区域仍需覆盖。 |
| 设置窗口位置与大小 | 通过 | A/B 均移动到指定位置，报告对应 frame rect。 |
| 窗口最大化 | 通过 | A 最大化后 frame 为 x=0、y=32、width=1280、height=768。GNOME 50 的 maximize/unmaximize 不传旧版标志参数。 |
| 发送虚拟键盘输入 | 通过（GTK 测试窗口） | 通过当前 Clutter seat 创建键盘，发送字符，B 中得到 `abc `；后续需验证组合快捷键、键盘布局和焦点切换。 |
| GTK 关键词文本替换 | 接口通过 | Shell 取得 `abc ` 的 surrounding text 与光标位置，通过 delete_surrounding + commit 得到 `2003 `。这是接口验证，没有实现完整匹配器或撤销。 |
| 非 ASCII 文本提交 | 通过 | 通过 inputMethod.commit 提交中文，得到 `2003 中文`。 |
| Rime 真实组合输入 | 通过（临时默认配置） | 在私有 IBus 中启用实际 Rime，输入 `nihao`。组合时 hasPreedit=true，已提交文本不变；空格确认后 preedit=false，中文出现在文本框及 surrounding text 中。临时默认 Rime 选词结果是“你哈哦”，本轮验证的是组合/提交分离，未使用用户个人词库。 |
| GTK 密码字段用途识别 | 部分通过 | Gtk.Entry PASSWORD 上报 purpose=8，带隐藏/敏感内容提示。尚未验证各应用密码字段，也没有实现或声称完整密码保护逻辑。 |
| 普通右键事件透传 | 通过（未拦截状态） | B 收到 1 次右键按下和 1 次松开。 |
| Stage 被动监听普通应用右键 | **不满足需求** | 同一时刻 Stage captured-event 的按钮计数为 0。应用事件由 Mutter 先处理，不能把这个信号当全局输入拦截器。 |
| 主动 Stage grab | 能拦截，但不适合作常驻方案 | Stage 收到按下/松开共 2 个事件，B 计数保持 1/1；同时 inputMethod 失去输入焦点。它会影响整套应用输入，而非只截取右键。 |
| 释放 grab 后重放普通右键 | 通过（测试窗口） | 再发送右键后，B 计数达到 2/2。只证明单次重放可达，不证明延迟点击与真实手势状态机已完成。 |
| evdev/uinput 权限 | 已确认权限限制 | 主机 `/dev/uinput` 为 root:root 0600；示例 `/dev/input/event0` 为 root:input 0660，当前用户不在 input 组。只检查了设备与权限，未打开、抓取或改权限。 |
| Firefox、终端、Electron、XWayland 文本替换 | 未验证 | GTK 测试不能替代这些应用的兼容性验证。不以退格模拟绕过无法识别的密码字段。 |

## 为什么 `captured-event` 不够

已核对与主机版本一致的 Mutter 50.5 源码：

1. `clutter_stage_handle_event` 在事件进入 Actor 信号链之前调用 `_clutter_event_process_filters`。
2. Mutter 的 `meta_display_handle_event` 可在 `meta_wayland_compositor_handle_event` 处理客户端事件后返回 STOP。
3. 新增 Clutter event filter 按注册顺序追加，并不自动位于 Mutter 的过滤器之前。

因此，不能将连接 Stage 信号或追加一个 filter 视为已解决全局右键拦截。Stage grab 可改变派发路径，但本轮确认了其对输入焦点的干扰。尚未排除所有可能的 Shell/native 接入方式；结论限于上述已测试路径。

## 第一阶段结束时推荐的下一轮验证

拆分为三部分：

- **最小鼠标输入服务**：获得指定鼠标设备的访问，使用 evdev 独占/转发与 uinput 处理右键。普通点击延迟重放；有效手势消耗右键并保持指针运动。必须验证辅助键、原始事件顺序、设备热插拔和服务退出后原鼠标恢复。当前仅是设计，尚未实测。
- **GNOME 扩展**：起点坐标与窗口命中、窗口对象管理、轨迹与反馈、快捷键/窗口动作、可用的文本输入协议接入。
- **普通用户进程与界面**：规则管理、匹配和声明式编排、应用启动、命令等；不放进有额外设备权限的组件。

输入服务的权限只服务于鼠标接入，不给 UI 或命令执行器提权，也不建议简单将用户加入能读取全部键盘设备的 input 组。用户已接受安装时的管理员授权；已准备 [鼠标输入验证工具](../probes/input/README.md)，采用独立 systemd 服务与仅授权用户可访问的控制 socket。尚未在宿主机安装，未添加 udev 规则或修改用户组。

文本替换优先验证已有 IME/surrounding-text 路径。对不提供周围文本或输入用途的应用，需要分别评估 IBus/应用协议接入，不能宣称所有应用可用，也不擅自取消此需求。Mozc、应用专属输入上下文、撤销和自身输入重入仍待验证。

当前仍不能认定全部开发前验证完成：右键完整捕获/透传、关键应用文本兼容及密码排除是后续门槛。

## 来源

以本机 50.5 实测及相同版本源码为主要依据；在线 API 文档会滚动更新，当前部分已显示 51，不能直接当作 50.5 兼容证据。

- [Mutter 50.5 官方源码](https://download.gnome.org/sources/mutter/50/mutter-50.5.tar.xz)：`src/core/events.c`、`clutter/clutter/clutter-main.c`、`clutter-event.c`、`src/wayland/meta-wayland-text-input.c`。
- [GNOME Shell 50.5 官方源码](https://download.gnome.org/sources/gnome-shell/50/gnome-shell-50.5.tar.xz)：`js/misc/inputMethod.js`、`js/ui/keyboard.js`。
- [GNOME 扩展调试说明](https://gjs.guide/extensions/development/debugging.html)：单独 Shell 会话与 GJS 进程范围说明。
- [Linux 内核 uinput 文档](https://www.kernel.org/doc/html/latest/input/uinput.html)：用户态虚拟输入设备机制。

## 鼠标输入验证工具准备状态

已准备 `probes/input/install.sh` 及其卸载入口，供用户在普通终端执行一次管理员安装。服务安装后默认空闲，不设置开机启动；只有控制器明确选择鼠标后才接管，单次最多 120 秒，控制连接租期为 3 秒。

元数据检查发现本机 Logitech G304 当前位于 event3，且声明键盘宏能力。原先拒绝所有混合能力接口的筛选会使当前鼠标无法参与验证，已修正为支持有 REL_X/REL_Y 和左右按钮的相对鼠标接口；从该接口收到的额外宏键原样转发，不参与手势，不监视独立键盘事件流。

已完成路由、控制 socket、超时清理、安装语法与 systemd 单元静态验证；真实设备拦截、鼠标加速度、菜单行为和实际断开恢复仍须用户安装后实测。没有宣称安装准备等于技术方案已经通过。

### 安装后 G304 识别故障

用户成功安装服务，但设备列表为空。主机能力元数据显示 G304 的 REL 为 0x1943，ABS 为 0x100000000（ABS_VOLUME），因此被旧版“任何 EV_ABS 都拒绝”的条件误排除。已修正为只拒绝绝对位置/多点触摸位置轴，同时镜像并透传非位置绝对轴；加入两项设备能力回归检查，原路由检查仍通过。服务当前保持空闲，修复需用户重新运行安装脚本同步至系统目录；无密码 sudo 不可用，尚未完成修复后的主机设备列表核对。

用户重新安装修复后，设备列表已成功返回 `/dev/input/event3 Logitech G304 usb-0000:00:14.0-11.2/input2:1`。设备枚举故障已解决；真实独占/转发、菜单行为和恢复仍待下一步手动操作验证。

### G304 实机拦截与透传结果

用户完成 60 秒验证并反馈要求的操作全部通过，菜单行为、指针手感和结束后的恢复正常。提供的输出包含 8 次点击、9 次轨迹；轨迹原始相对移动长度为 120.1～344.3，点击为 0～1。两次轨迹记录辅助码 272，即 BTN_LEFT（左键）；用户总体反馈辅助键测试通过，但本段日志没有单独记录 BTN_SIDE/BTN_EXTRA，侧键码仍可在后续集成测试中核对。最后自动超时释放物理鼠标。

至此，真实 G304 的 evdev 独占 + uinput 转发链路已取得实机证据，普通右键、移动期间右键消耗、左键辅助组合和超时恢复通过。没有据此认定窗口起点绑定、形状识别或正式动作执行已经完成。

用户观察松开后约 0.5 秒才输出。代码核对发现 Router 在 BTN_RIGHT 松开事件中同步生成记录，而控制器在每次读取结果后固定睡眠 0.4 秒；显示轮询足以造成这一级别的可见延迟。将控制器轮询间隔改为 20 毫秒，作为探针反馈改进；当前系统服务协议兼容，因此可直接运行项目中的新 client.py，无须为本次改动重新安装特权服务。此说明不替代真实释放到动作执行的端到端延迟测量。

## 第二阶段暂停时的记录（2026-10-13，已恢复）

用户出门时明确要求暂停；以下保留当时进度。用户随后要求继续，最新状态见后面的恢复结果。

已保存第二阶段探针 `probes/gnome50/stage2.py`，扩展新增 bind-start/bound 接口，浏览器测试页和终端专用输入接收脚本。使用临时 XDG 目录、私有 D-Bus 与单独 headless GNOME Shell。为了验证真实应用启动，部分测试在沙箱外运行；没有安装测试扩展到主桌面，也没有接管真实鼠标。

当前已取得的证据：

- 窗口接口：起点坐标 (200,300) 命中 Probe A，焦点仍为 Probe B；移动到 B 后，绑定的 stableId 与窗口 A 保持不变；关闭 A 后 alive=false，未回退到 B。
- Firefox 普通网页输入框：surrounding text 与光标可读取，abc 空格替换为 2003 空格成功；Rime preedit/commit 分离可见，密码字段上报 purpose=8 与隐藏/敏感 hints。
- 浏览器 DOM value 在组合时可包含预编辑中文字，而 Shell surrounding text 仍仅含已提交内容，不能将 DOM 显示值视为提交状态。
- VS Code 1.141.0（Electron 原生 Wayland，临时用户数据，禁用第三方扩展）：专用文件实际保存为 abc 空格，替换后保存为 2003 空格；其 surrounding text 包含 Monaco 的额外上下文，不能假设其等于文件全文。测试设置启用了 Wayland IME/text-input-v3，尚未比较默认启动参数，也未测试 Electron 密码输入框。

尚未完成与需要恢复的工作：

1. Ptyxis 50.1 的专用命令没有成功启动。沙箱内先遇到 newuidmap 限制；改在主机的私有会话中运行后仍显示终端标题 `(Failed)`，没有生成 terminal.json。**这是测试进程启动故障，不能判作终端不支持文本替换。** 当前需要继续排查 Ptyxis agent/会话容器及命令启动；最新截图 `/tmp/waystroke-stage2-tqnbj9tq/terminal.png`，源码在 `/tmp/waystroke-sources/ptyxis-50.1/`。
2. 当前绑定结果仅是 GNOME 接口测试，尚未把已安装鼠标服务的真实右键开始事件与 GNOME 起点快照完整连接。必须解决跨进程通知与指针移动的时序，不能在手势结束时取窗口，也不能忽略开始通知的延迟。
3. Electron 的 Rime/密码字段、Firefox 多行与 contenteditable、终端兼容、XWayland 尚需按必要性继续验证，不重复已通过的整套鼠标测试。

已保存原始阶段结果：`probes/gnome50/results-stage2-apps.json`（含 Firefox、Code、终端启动失败）及 `results-stage2-terminal.json`（仅重跑终端与窗口绑定）。第二阶段尚未完成，不据此标记正式开发前验证全部通过。

测试会话按运行器 finally 清理其启动的进程。用户已安装的鼠标输入服务仍是独立验证服务，本阶段没有启动真实鼠标接管。

## 第二阶段恢复结果（2026-10-13）

### Ptyxis 与终端文本路径

启动故障根因是 Ptyxis 启动子命令时使用用户 systemd scope，临时 XDG_RUNTIME_DIR 没有宿主用户管理器的 socket。为独立测试运行器接入宿主用户 bus/systemd socket 后，专用接收脚本成功启动；其应用 D-Bus、显示、配置仍属于私有测试会话。没有修改用户 systemd 配置。

- Ptyxis 50.1 接收 `abc ` 成功，上报 TERMINAL purpose=10、hasFocus=true，但 surrounding text 为 null。因此不调用 delete_surrounding；不能使用浏览器/GTK 同一条周围文本删除路径。
- 真实 Rime 在终端中产生 preedit，确认后提交中文；组合期间专用接收脚本没有收到尚未提交的文字。
- 独立 readline 接收脚本中，输入 `abc `，发送四次退格再提交 `2003 `，最终接收行确实为 `2003 `。证明此类行编辑场景可以使用替换路径，未实现完整关键词匹配、撤销或敏感输入保护，也不能推广到所有终端程序。
- 在测试无 surrounding text 的删除接口时，独立测试 Shell 曾异常退出。扩展探针已明确拒绝该调用；后续验证使用可用的行编辑路径。主桌面未受影响。

原始证据：`results-stage2-terminal-ready.json`、`results-stage2-terminal-line.json`。终端的安全替换策略仍需区分应用场景，不能因为有退格路径就默认在终端密码提示中启用。

### 起点窗口的输入时序

已为鼠标服务加入协议 v2：右键开始后发送 begin，暂存后续事件；GNOME 完成起点快照后，控制器用对应 sequence 确认，服务再继续转发。超过 250ms 没有确认会释放物理鼠标。旧的普通 watch 模式保持无需握手。

独立真实 GNOME + 模拟输入服务检查通过：焦点为 B、起点在 A；人为推迟处理开始通知 40ms，并提前送入跨窗移动与松开事件，快照仍绑定 A，确认后终点才移到 B。证据见 `results-binding-ordering.json`。这证明探针的队列顺序，不替代真实 uinput/Mutter/预览窗口转发的端到端验证。

独立桌面的 mutter-devkit 可见预览已成功启动，见 `results-binding-viewer.json`。安装与人工验证入口为 `probes/gnome50/install-binding.sh`、`binding.py`，步骤见该目录 README。当前已安装服务尚未同步这次协议升级；需用户执行安装命令。

### 锁屏及剩余门槛

用户当前锁屏，本轮只运行独立测试会话，没有接管真实鼠标或向主桌面发送键盘输入。联动控制器在锁屏时拒绝启动，运行期间每 0.5s 检查并停止；这是探针行为。正式产品应通过 GNOME 锁屏事件立即取消手势和动作、释放设备、清除文本上下文，解锁后不重放旧输入。

下一项是解锁后的真实鼠标起点窗口联动。之后仍需必要的 Electron 输入法/敏感字段、Firefox 多行/contenteditable、快捷键组合，以及文本替换敏感场景验证。XWayland 能力尚未验证。第二阶段尚未完成，不把隔离接口证据视为完整产品实现或全部验证通过。

## 第二阶段补充检查结果（2026-10-13）

用户要求先完成可以自动执行的检查。所有输入仍发生在独立 GNOME 会话、专用页面/文件/终端脚本内，没有接管物理设备。下表替代上一节的相关待验证项。

| 检查 | 实测结论 | 范围与限制 |
| --- | --- | --- |
| Firefox textarea 实际换行文本 | 通过 | `前文\nabc ` 替换为 `前文\n2003 `，前面的中文和换行保留。 |
| Firefox contenteditable | 通过 | 光标在已有 `Editable` 前，输入并替换后得到 `2003 Editable`，尾部原文保留。 |
| Electron HTML 编辑与敏感输入 | 通过（本机运行时） | 使用本机 Code 自带 Electron 43.7.7 / Chromium 150.0.7871.250 的专用应用；textarea/contenteditable 替换成功，密码字段 purpose=8、hints=6144，探针拒绝替换，字段长度仍为 0。不能推广到不提供相同协议的其他应用。 |
| Electron Rime | 通过 | preedit=true 时替换请求被拒绝；空格后 preedit=false，最终文本提交中文。显式开启 Wayland IME/text-input-v3 与不加这两个参数的 Wayland 启动均成功；默认模式仍指定了 Wayland 后端。 |
| VS Code 编辑器 Rime | 通过（专用文件） | 文件从 `2003 ` 到 `2003 你哈哦` 实际保存成功，组合期间 Shell 上报 preedit=true。组合期间磁盘文件仍为此前保存内容，这不等于实时编辑器缓冲区未变；正确保护依据是 preedit 状态。Monaco surrounding text 有额外上下文，不可当作文件全文。 |
| Ctrl+A、Shift、Ctrl+Shift+Left | 通过 | Ctrl+A 后输入覆盖原文为 replacement；Shift 输入得到 replacementZ；Ctrl+Shift+Left 选中前词后输入得到 end。Code 的 Ctrl+S 也有实际保存证据。不是对所有系统/应用快捷键的穷举。 |
| 键盘布局 | 通过（US/FR） | 同一个 evdev 物理键码 16，通过 Clutter.notify_key 在 US 产生 q，在 FR 产生 a；实际文本分别为 endq/endqa。按物理位置发送与按字符键值发送必须在实现中区分。 |
| 终端无回显密码提示 | **无法依靠 Shell 用途保护** | 专用 getpass 脚本确认提示阶段 ECHO=false，Shell 仍报告 purpose=10、hints=0、surrounding=null；输入结束后回显恢复。仅记录固定测试文本长度，没有记录其内容。不能据此为终端开启未知上下文的自动退格替换。 |
| XWayland 窗口与键盘 | 通过（GTK 代表应用） | clientType=1；焦点 B、起点命中 XProbe A，跨到 B 后 stableId/title 仍为 A；最大化和字符 abc 空格均成功。 |
| XWayland GTK 文字替换 | **现有 Shell 接入路径不可用** | 窗口聚焦后 Shell inputMethod hasFocus=false、surrounding=null；替换请求被拒绝。字符输入成功不代表能够获取文本、检测密码或可靠替换。需要额外输入法/应用接入路径。 |

XWayland 初次测试遇到独立 headless 环境的 NVIDIA EGL 崩溃；仅对测试会话设置 XWAYLAND_NO_GLAMOR=1 后运行软件渲染，再使用测试 Shell 自己的 DISPLAY/XAUTHORITY，窗口检查完成。没有修改主桌面的 GPU、XWayland 或认证配置。

多行测试发现探针的 gdbus 参数会把 JSON 转义换行再解码，导致 JSON.parse 拒绝请求。已将 stage2 的请求参数改为 GLib.Variant 的字符串表示，随后实际多行测试通过；这是测试传输层修复，不是浏览器能力故障。contenteditable 早期检查误用 endswith 判定，实际替换发生在已有文字前；已改为核对完整预期字符串，原始观察内容保持不变。

新增原始结果：

- `results-stage2-firefox-extra.json`：多行、contenteditable、组合状态/敏感字段、快捷键、布局。
- `results-stage2-electron.json`、`results-stage2-electron-default.json`：两种启动参数对照，含实际运行时版本。
- `results-stage2-code-ime.json`：Monaco Rime 和实际文件保存。
- `results-stage2-terminal-password.json`：关闭回显阶段与 Shell 用途对照。
- `results-stage2-xwayland.json`：窗口、键盘及文本接口的正反向证据。

结论：本轮代表性应用的自动检查已经完成，既有通过项也有明确不可用项。**整个开发前技术验证仍未全部通过**：终端敏感输入与 XWayland 自动补全的可靠接入仍是开放技术问题。不能将应用范围缩减、手动退格或“以后适配”当作解决方案，也不要求用户反复安装重测这些已经取得结论的自动项目。

测试应用打包方式参考 [Electron 官方应用分发说明](https://www.electronjs.org/docs/latest/tutorial/application-distribution)，最终兼容结论以本机运行时实测为准。

## 第三阶段：补全接入路径

第二阶段的两项缺口没有用全局退格兜底。本阶段继续使用专用窗口、私有显示/会话/无障碍总线与固定文本，主桌面没有新增扩展、键盘监听、Shell 配置或物理设备接管。

### XWayland 的 AT-SPI 编辑

使用本机 at-spi2-core 2.60.7。运行器显式启动自己的 at-spi-bus-launcher 和 registryd，并将 GTK 客户端和检查进程连接至该私有总线。初次 registry 激活失败属于运行器隔离配置问题；显式启动后取得窗口和字段，而不是将空树判为应用不支持。

- XWayland GTK 和原生 Wayland GTK 的正常文本节点提供 Text、EditableText，焦点和光标位置可读取。删除 `abc ` 并插入 `2003 ` 后，两次操作均返回 true。
- 密码节点角色为 PASSWORD_TEXT；检查程序先检查角色，不调用其 Text 读取/编辑方法。
- 最小自动监听器接收 object:text-changed，只在指定测试窗口的已聚焦可编辑节点检查固定关键词。`abc ` 自动变为 `2003 `，密码框中的相同固定输入保留不变。没有读取或保存事件 any_data，避免依赖可能包含输入文字的事件载荷。
- XWayland GTK 的 IBus/Rime 组合期间，AT-SPI 文字仍是已提交的 `2003 `，空格提交后变为 `2003 你哈哦`。这只证明此 GTK 节点没有把 preedit 当已提交文本，不代表 AT-SPI 自带通用组合状态。

证据：`results-stage3-a11y-x.json`、`results-stage3-a11y-native.json`、`results-stage3-a11y-auto.json`、`results-stage3-a11y-ime.json`。

### Enter 确认的顺序

只监听文字变动不足以识别 Gtk.Entry 的 Enter：它不插入换行，而会直接触发 activate。旧 AT-SPI keystroke listener 在独立 XWayland 中注册返回 false，因此未把它当正式可用方案。Mutter 当前 KeyboardMonitor 的访问控制只允许指定调用者，产品不能冒用 Orca 的总线名或关闭访问控制来获得权限。

另一个正常接入点已实测：GNOME 扩展调用 Meta.Display.grab_accelerator('Return', NONE)，通过 Main.wm.allowKeybinding 在 NORMAL 模式接收按键。后台完成编辑后，扩展临时将该绑定设为 NONE，重放 Enter，再在空闲回调恢复 NORMAL。XWayland 使用虚拟键盘；原生 Wayland 使用 Main.inputMethod.forward_key 的已处理按键路径。

实测证据：

- 原文 abc，物理路径的虚拟测试 Enter 已被保留时，字段 activate=0。
- AT-SPI 完成替换再重放后，activate=1，activatedText=2003。说明替换发生在确认前，而不是提交后再改文本。
- 密码框 abc 被跳过，重放后 passwordActivate=1、passwordActivatedLength=3。
- 未匹配的 plain 重放后正常确认，activatedText=plain，正常字段累计 activate=2；捕获事件计数与三次测试确认相符，没有重放循环。

以上是隔离接口与顺序证据，不是正式调度器或完整按键延迟承诺。实现时应按匹配状态启用最小确认键集合，并处理绑定冲突、焦点变化、控制器失联和锁屏，不能常驻吞掉所有 Enter。测试扩展仅在其临时 GNOME 实例中启用。

证据：`results-stage3-a11y-enter.json`、`results-stage3-a11y-enter-native.json`。

原生 Wayland 的第一次对照发现：虚拟键盘重放会再走一遍异步 IBus，空闲回调先恢复绑定，随后未处理的 Enter 又被 accelerator 捕获，导致应用 activate=0、捕获记录多一条。根因是把“虚拟事件已排入队列”误当作“输入法处理结束”。改用输入法已处理按键接口后，activate=1、activatedText=2003，捕获记录保持一条；密码和未匹配文字也正常确认。没有通过扩大固定等待时间掩盖该异步顺序问题。

原生 Rime 组合时，Enter 直接由输入法消费，未产生新的 accelerator 捕获。字段从 abc 加组合 nihao 到 abcnihao，activate 仍为 1。因此不能把旧捕获记录当作本次确认，也不应再次人为重放输入法已经消费的 Enter。

### XWayland Rime 的组合保护

普通 IBus AddMatch 订阅和 GDBus message filter 未观察到 GTK 当前组合的完整可见状态，不能以 matchAccepted=true 声称保护成功。核对本机 IBus 1.5.34 源码发现，GTK 的同步后处理路径可通过 PostProcessKeyEvent 返回组合更新，不保证发出对应信号；不能另外读取这个队列来抢走客户端更新。该失败证据保留在 `results-stage3-ibus-observer.json`。

GNOME 自己的 IBus PanelService 能提供候选/预编辑可见状态。探针连接该已有对象，只使用可见布尔值和焦点上下文，不读取预编辑内容。原生应用优先使用 Main.inputMethod.hasPreedit；XWayland 的当前 Rime 使用面板可见状态作为保守的额外阻止条件。

测试：先在 GTK 文本框留下 abc，再组合 nihao。此时 Shell hasFocus=false、preedit=false，但 PanelService lookupVisible=true；Enter 的捕获记录 imeGuard=true。控制器跳过 abc 替换，把 Enter 交还输入法，最后字段为 abcnihao（Rime Enter 提交拼音），activate 仍为此前的 1，没有把组合确认当作应用提交，也没有把前面的 abc 改成 2003。

这是**本机 Rime 的保护证据**；候选可见不等价于所有输入法的 preedit。其他输入法或无法确认状态的上下文不得据此标为完全支持，需要更明确的组合接口或暂停替换。证据：`results-stage3-a11y-enter-rime.json`。

### 终端 Zsh 行编辑接入

专用脚本只使用临时 Zsh -dfi 和 vared/ZLE，不加载或修改用户配置，不把捕获的文字当命令执行。固定规则在 ZLE widget 内修改 LBUFFER，再调用原有 self-insert/accept-line：

- 空格确认：abc 空格得到 2003 空格。
- Enter 确认：abc 得到 2003，随后正常接受该行。
- Rime 组合/提交：preedit=true 到 false，ZLE 最终收到已提交的中文“你哈哦”。
- 同一 Shell 的 read -s 隐藏输入 abc 长度仍为 3，没有触发替换。
- 外部 Python getpass 子程序确认 ECHO=false，输入 abc 后长度仍为 3；两个子程序场景都没有额外执行替换 widget。总替换次数仅为前两个普通行编辑测试的 2。

这条路径不需要监视物理键盘，不依据终端的 TERMINAL 用途猜测密码状态，也不修改终端程序内部。它需要显式 Shell 集成，覆盖的是该 Shell 行编辑器；其他交互式 CLI、编辑器或远程程序不自动因此获得补全。

证据：`results-stage3-terminal-zle.json`。曾向用户提出产品范围问题：是否接受可选 Zsh 集成、命令行编辑区域补全、其他终端子程序默认不替换。用户随后明确允许普通及密码终端输入都自动替换；继续验证通用终端路径，不再以识别密码为前置条件，也不把只支持 Zsh 的方案视为已接受范围。完整终端验证尚未完成。

### 接入建议与边界

鼠标仍使用独立受控设备服务；GNOME 扩展负责起点窗口、输入/窗口动作、确认键与输入法状态。普通用户后端负责规则、编排和文字适配器：原生文本协议优先，已验证的 AT-SPI 节点用于 XWayland 回退；终端继续验证通用输入路径，ZLE 作为已有的确定性方案。没有增加 root 键盘采集器的必要实测依据。

这些结果确立代表性窗口和字段的可行路径，不能推广为所有应用、所有输入法均可编辑。正式实现必须通过实际能力显示可用/不可用原因，不能向未知上下文发送退格，也不能静默删除需求。

参考的当前版本源码与官方接口：

- [AT-SPI EditableText](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/iface.EditableText.html)：本机实际返回值和角色为最终证据。
- [AT-SPI keystroke listener](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/func.register_keystroke_listener.html)：本机该路径注册失败，未采用。
- [Zsh ZLE 官方说明](https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html)：vared、widget、LBUFFER 与原有编辑动作。
- [IBus 1.5.34 源码](https://github.com/ibus/ibus/releases/tag/1.5.34)：bus/inputcontext.c、client/gtk2/ibusimcontext.c。

## 第四阶段：允许终端密码替换后的通用路径

用户明确允许终端普通输入、密码输入均自动替换。该决定解除终端的敏感用途识别前置条件，未授权把其他应用的密码保护也整体取消。此前询问“只支持 Zsh”不再作为待确认范围。

探针在独立 GNOME 的 Main.inputMethod.notify_key_event 路径中观察输入法未消费的终端按键，并接收该上下文的 commit-text。只对 TERMINAL 用途的焦点跟踪固定关键词，不读取物理键盘，也不记录原始按键或输入内容；密码固定测试仅保存长度及是否得到预期内容。Space/Return 使用已验证的 accelerator 确认路径。它是固定规则接口探针，不是完整关键词引擎。

最初将三次虚拟退格和 inputMethod.commit('2003') 混用，子程序实际得到 abc2；原始字节证据为 abc2003 后才到达三次 DEL。根因是键盘事件与 text-input 提交属于不同通道，提交可以先于程序处理退格。未增加任意固定延迟兜底，改为在本机 VTE 中一次提交 DEL×3 + 2003，保证送入 PTY 的字节顺序，再重放确认键。

本机 Ptyxis 50.1/VTE 的实测结果：

| 场景 | 实际结果 | 结论 |
| --- | --- | --- |
| 普通 canonical 输入，空格确认 | 2003 空格 | 通过 |
| 普通 canonical 输入，Enter 确认 | 2003 | 通过，Enter 正常接受该行 |
| Python Readline，空格确认 | 2003 空格 | 通过，不依赖 Zsh widget |
| Python getpass，空格确认 | 长度 5、预期匹配=true | 固定密码输入替换通过 |
| Python getpass，Enter 确认 | 长度 4、预期匹配=true | 固定密码输入替换通过 |
| 真实 Rime，随后普通关键词输入 | 你哈哦 空格 2003 空格 | 组合时 preedit=true，提交后的输入跟踪与替换通过 |
| 不提供行编辑的 raw 输入程序 | abc + DEL×3 + 2003 + 空格 | 删除字节顺序正确，但程序不解释为删除；不能算作正确文字替换 |

原始结果保存在 `probes/gnome50/results-stage4-terminal-generic.json`。使用专用 Python 脚本按上述模式读入固定文本；没有执行这些输入行，没有把密码内容写入结果文件，没有安装/修改个人 Shell 配置或主桌面扩展。

结论：当前终端的常见行编辑和密码场景已有不依赖 Shell 集成的可行路线，敏感用途不可识别不再是用户要求下的阻断点。**“允许替换所有输入”仍不等于“所有程序都会正确编辑”**：raw/TUI/编辑器可能把 DEL 当普通字节或命令；其他终端的输入协议与删除字节设置也不能直接按 VTE 结果推广。通用路径可以作为本机 VTE 的适配方案，ZLE/应用集成仍可提供更精确的编辑能力。

正式实现需区分通用输入跟踪与真实文档内容：焦点变化、粘贴、光标/历史导航和快捷键后不能拿旧缓存当真实光标周围文本；按规则应用范围与实际适配能力执行。上述探针只覆盖固定关键词与必要的代表性输入，不声称这些产品状态机已实现。

## 第五阶段：XWayland 无编辑接口应用的回退路径

2026-10-22 在 mutter-devkit 独立会话中验证。对象是既没有 AT-SPI Text/EditableText、也不经过 Shell 输入法 surrounding text 的 XWayland 程序。分两层：先确认哪些工具包其实能提供编辑接口，再验证其余程序的“选区校验替换”前提。探针、夹具和原始结果见 `probes/xwayland-fallback/`。没有修改产品代码，也没有改动主桌面。

### 第一层：工具包是否已有编辑接口

| 对象 | 结果 |
| --- | --- |
| Qt 6.11（PySide6，xcb） | 辅助功能总线 `IsEnabled=false`、`ScreenReaderEnabled=false`、未设 `QT_LINUX_ACCESSIBILITY_ALWAYS_ON` 时仍注册 AT-SPI；Text/EditableText 删除、插入成功，应用内容变为 2003。打开开关或设置环境变量的结果相同。Qt 5 未测。 |
| GTK4（X11，参照） | Text/EditableText 可用，与现有 AT-SPI 路径一致。 |
| Tk 9.0 | 不注册 AT-SPI。 |
| Java Swing（Temurin 17） | 不注册 AT-SPI。Fedora 44 仓库已无 `java-atk-wrapper`，用户无法一键打开 Java 辅助功能。 |
| Chrome 155、VS Code 1.141 | 默认即为原生 Wayland（clientType=0），不加参数时 Shell 输入法即可读到 surrounding text `abc`，属于现有原生路径，不需要辅助功能。自带旧版 Electron 的程序未测。 |

因此当前环境不需要为 Qt 写入全局开关，也不需要为 Chromium/Electron 打开辅助功能（性能开销问题随之消失）。真正缺少编辑接口的是 Tk、Swing 及 Wine、自绘控件一类程序。

**附带发现（影响现有密码保护的依据）：** GTK4 `Gtk.PasswordEntry` 的焦点节点角色是 `text box`，Qt 密码 `QLineEdit` 是 `text`，都不是 PASSWORD_TEXT；读取到的文字分别为 `●●●` 与 `•••`。`crates/core/src/atspi.rs` 以角色 40/60 跳过密码字段，对这两类控件不会生效；实际阻止替换的是掩码文字永远匹配不上关键词。现有 GTK 测试夹具使用 `Gtk.Entry(visibility=False)`，它确实报告 PASSWORD_TEXT，所以未暴露此差异。是否补充其他识别依据需另行决定。

### 第二层：选区校验替换

流程：XWayland 辅助客户端通过 XI2 raw 按键记录输入；确认键触发且缓冲末尾匹配关键词（n 个字符）时，先占有 PRIMARY，再发 `Shift+Left ×n`；读取 PRIMARY，内容等于关键词才输入替换文字，否则发 `Shift+Right ×n` 还原。实测得到的前提与修正：

- **按键来源与隐私边界：** XWayland 2.0 的 raw 事件能还原 `hi aBc`（含 Shift）；焦点在原生 Wayland 窗口时收到 0 个 raw 事件，不覆盖原生程序。
- **处理完成的判断：** 只等选区所有者变化不够。Tk、Swing 在第一个 `Shift+Left` 后就接管 PRIMARY，并且在按键尚未处理完时就回答选区请求，因此读到 `c`。raw 事件屏障（全部选区按键已送达客户端，约 1ms）对 Qt 足够，对 Tk/Swing 不够。采用“重复读取直到等于关键词”：观察到的选区单调增长（`c`→`abc`）；关键词每个字符都是单一码点时，较短的中间状态不可能等于关键词。Tk 保持所有权时不会再发通知，所以每次需先由探针占有 PRIMARY。
- **Tk、Qt、Swing 各 10 次连续替换全部成功。** 从发出选区按键到校验通过：Qt 7–24ms（中位 13），Tk 21–36ms（中位 26），Swing 20–34ms（中位 30）；选区高亮约持续 1–2 帧，截图见 `visual-selection.png`。Enter 确认时应用 activate 收到 2003。
- **粘贴：** Tk 的 Ctrl+V 不替换选区而在光标处插入（得到 `中文👍abc`）；改为 BackSpace 删除选区后粘贴，三者均得到 `中文👍`。
- **密码字段：** Tk 导出 `***`、Swing 导出 `•••`、Qt 不导出，均校验失败而不编辑，`abcZ` 原样保留。
- **不匹配与行首：** `abd` 与只有 `ab` 时校验失败，还原后继续输入得到 `abdZ`、`abZ`。
- **程序冻结：** SIGSTOP 期间超时不编辑；恢复后排队的选区/还原按键相互抵消，得到 `abcZ`。
- **Unicode：** Qt、Swing 的 `Shift+Right` 能精确抵消 `Shift+Left`（含 `👍🏽`）。Tk 不能：`x中文👍🏽` 在选中再还原后仍残留选区，下一次输入吞掉 `👍🏽`。仅在缓冲推测错误、光标前恰有多码点字符且为 Tk 时触发，但属于数据丢失风险。
- **撤销：** Qt 的 Ctrl+Z 恢复为 `hi abc`；Tk、Swing 字段默认无撤销。
- **终端：** xterm 不导出选区，程序收到 `ESC[1;2D`×3 与 `ESC[1;2C`×3；WM_CLASS 为 `XTerm`，`_NET_WM_WINDOW_TYPE` 为空，窗口类型无法区分终端。默认开启前必须可靠排除终端类程序，目前只能依靠类名名单。
- **用户在校验期间继续输入：** 用第二个虚拟键盘模拟。按键在选区已校验后、替换完成前到达时，raw 事件的送达顺序可以还原客户端实际内容（`x2003`、`xy2003`），再选中并校验这一段后改写为 `2003x`、`2003xy`；Tk、Qt、Swing 均验证通过。按键在校验完成前到达时（Tk 的窗口约 26ms），关键词已被用户字符覆盖，而内容从未经过校验，不能补救，结果为 `x`。目前没有在这段时间截留发往客户端按键的已验证途径：此前 Shell `captured-event` 与 Clutter 过滤器实验均收不到客户端输入，Stage grab 会使应用失去输入焦点；本阶段未另行验证新途径。
- **GTK4 X11** 对 UTF8_STRING 请求返回空的 PRIMARY，此路径不适用；GTK 已有 AT-SPI。

结论：选区校验替换对 Tk、Qt、Swing 可以做到“只在校验通过后编辑”，密码、冻结、不匹配均安全失败；剩余风险是校验期间的并发输入（无法补救的窗口约 10–35ms）、Tk 的多码点字符还原，以及终端识别。不能宣称完全无感。

### 实现结果（2026-10-22）

用户决定默认对所有应用启用、在设置中按应用排除，以免逐个配置新程序。默认启用的代价由以下措施限定：内置 X11 终端名单；每次只先发一个 Shift+← 探测，不导出选区的窗口只多收到一对 Shift+方向键，连续三次后停用并在运行状态页提供一键排除；关键词限于单码点字符，Tk 的多码点还原问题不会发生在关键词本身；前一字符未知时用一次额外选中检查词边界，用 Shift+→ 能否缩短选区区分字段开头与响应慢的程序，避免依赖固定等待。AT-SPI 报告密码字段或暂不可编辑的文本节点时不回退。

实测（`fixtures/xwayland-selection/`）：Tk、Swing 的确认、撤销、粘贴、密码、边界、立即规则与排除全部通过；xterm 只收到原输入；不导出选区的窗口恰好收到三对 Shift+方向键后停用。不匹配时 Space 的等待为 6–33ms，在这段时间内按下的键会排到 Space 之前（现有 XWayland 确认键路径同样如此，结果是不替换，不丢字）。空格后 10–80ms 按下的键都在替换完成后到达，结果正确；按送达顺序修正插入按键的逻辑由单元测试覆盖，最终端到端运行中未出现需要修正的时序。

实现中补充发现：选区在字段开头截短后按发送次数还原会越过原光标、选中其后的文字，现按读回选区的光标步数还原；Tk 在光标前为多码点字符时 Shift+→ 无法缩短选区（与位置无关地复现），追加一次 → 与 ← 后不再残留选区，文本末尾时光标提前一位但不丢字。原先“对 Tk 不还原、直接放弃”的建议会留下选区，下一次按键会覆盖它，因此没有采用。

## 真实鼠标起点联动结果

用户提交了 event7 的完整记录，保存于 `probes/gnome50/results-binding-user.json`：

- 两次跨窗轨迹：开始焦点为 Probe B，坐标命中 Probe A；结束坐标命中 Probe B，绑定 title=Probe A、stableId=1 保持不变。原始移动长度分别为 313.9、333.5。
- 两次普通点击：移动长度为 1.0、0.0，均输出 click，目标保持 A。
- 四次 bindingMs 为 5.4、5.4、4.7、4.5ms。该指标从控制器处理 begin 开始，包含快照请求和确认握手；不包含此前通知等待，也不是松开到动作执行的端到端延迟。

真实鼠标经 uinput、预览窗口转发至独立 GNOME 的起点绑定已经取得正向实机证据。此记录未包含手感、意外菜单、终止后恢复的文字反馈，不据此重复宣称这些主观/恢复项已重新确认；此前单独鼠标探针已有用户通过反馈。仍未在主桌面安装扩展或证明任意主桌面窗口场景均兼容。


### 2026-10-22：修饰确认键与微信选区修复

原生 `notify_key_event` 和 TERMINAL 适配器原先只排除 Ctrl/Alt/Super，因此 Shift+Enter 会进入确认：原生未匹配以 `forward_key(..., 0, ...)` 丢失 Shift，终端未匹配则提交 `\n`，绕过应用的修改键处理。原生 Electron（包括声明普通文本用途的集成终端）可能走前者，Ptyxis/VTE 的 TERMINAL 焦点走后者；XWayland 的 `x11_replay` 已传有效/原始修饰状态，原先不具备同样的硬编码丢失问题。现在在原生入口和 XWayland 绑定过滤器直接透传修改键组合，普通确认重放也保留修饰。使用真实 Shell/IBus 输入路径验证，具体结果见 `fixtures/text-compatibility/`。

用户报告的“此窗口没有导出选区”来自第一步 Shift+← 后 150ms 内未收到 PRIMARY 所有权通知，发生在读取文本格式之前。隔离的微信 4.1 只能到二维码登录界面，因此在用户同意后于主桌面只读观察 XFixes 选区所有者变化（不读内容、不发输入）：微信的选区所有者窗口为 “Qt Selection Owner for wechat”；在聊天输入框中键盘选择与鼠标拖选都没有设置 PRIMARY，只有 Ctrl+C 设置 CLIPBOARD（`fixtures/text-compatibility/wechat-session-selection.json`）。所以不是延迟导出，延长探测时间无效。

对微信改用复制读回：不探测 PRIMARY，直接选中关键词，规则要求词边界且前一字符未知时多选一个字符；Shell 先备份剪贴板全部数据格式，再发一次 Ctrl+C，只接受新的所有者变化（旧剪贴板即使等于关键词也不采用），读回后恢复备份。这一次读回同时完成关键词校验和边界判断：读回为“前一字符+关键词”时按前一字符决定替换或还原，恰好等于关键词时说明字段开头挡住了多出的 Shift+←。Ctrl+C 与 Shift+← 经同一虚拟键盘按序送达，复制时已包含全部选择键。300ms 等待只从备份完成后计时，备份慢不会被误判为不导出。每次替换因此只有复制和恢复两次剪贴板所有者变化；复制本身仍会进入 CopyQ 等剪贴板管理器的历史。Codex 初版对探测、校验、边界各复制一次，一次替换可能复制三次以上，已改为单次。

复制选区夹具（窗口类 WeChat、关闭 PRIMARY 导出、只响应 Ctrl+C）在 devkit 中验证空格/Enter、字段开头、撤销、Unicode 粘贴、词边界、旧剪贴板、无导出上限、文本/HTML/二进制格式恢复，以及一次替换只有两次所有者变化。登录后微信聊天框的最终替换仍需用户实机确认。
