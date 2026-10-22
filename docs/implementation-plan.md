# WayStroke 完整开发与验收计划

状态：2026-10-13，计划已落地，正式工程阶段 A 已完成。本计划覆盖全部已确认功能；阶段完成不等于产品完成。任务状态以文末实施记录为准；验证探针不计作正式功能交付。

用户硬性要求：**正式 UI 与最终 HTML 设计稿一比一复刻，且不得交付空壳。** 每个可操作控件必须连接真实配置、真实后台或真实桌面能力；不能以占位成功、固定结果或只有界面代替实现。原型中的窗口外评审工具不属于产品，窗口内示例值在正式应用中绑定真实数据。

需求依据：[产品规格](product-design.md)、[69 项动作目录](action-catalog.md)。界面依据：`design/` 的窗口客户区、页面、弹窗与状态。技术依据：[验证结果](technical-validation.md)及 `probes/` 原始记录。

## 技术栈与组件

| 组件 | 实现 | 职责与权限 |
| --- | --- | --- |
| 设置应用 `waystroke` | Tauri 2、TypeScript、Vite、HTML/CSS | 复刻设计稿、编辑配置、预览和显式测试；普通用户权限 |
| 后台 `waystroke-core` | Rust | 配置、识别、规则匹配、编排、普通用户动作执行、运行状态；不依赖设置窗口存活 |
| GNOME 扩展 `waystroke@local` | GJS | 起点窗口与窗口对象、桌面输入、轨迹反馈、输入法状态、确认键、锁屏通知；仅适配 GNOME 50.5 |
| 鼠标服务 `waystroke-inputd` | Rust、evdev/uinput | 选定相对鼠标的接管、转发、主键/辅助键状态和安全释放；独立特权 systemd 服务 |

前端使用模块化 TypeScript，不先引入新的页面框架；保留设计稿的 DOM 结构、CSS 和交互流程。原型全局函数、浏览器存储和样本反馈逐项替换成真实模型与接口，不把原型业务逻辑整体搬进正式后端。

Rust 使用 Cargo workspace，桌面接入使用 D-Bus（zbus），配置与协议使用类型化 serde 数据。AT-SPI 适配首先实现已验证的 D-Bus 方法/角色/事件；Rust 绑定的实际返回结构与焦点身份在第一批集成中核对，Python GI 探针是对照证据，不是隐含的正式运行时依赖。

Tauri 只作为桌面壳和受限本地接口，不承担全局键盘或窗口管理。构建启用需要的 WebView/D-Bus 能力，不依赖 X11 输入自动化或第三方托盘扩展。应用强制使用原生 Wayland，并在独立 GNOME 中核对 clientType=0。

关闭设置窗口后后台继续按已保存配置运行；“退出 WayStroke”才停止本会话的功能并释放设备。自动启动采用用户服务/会话入口，按设置开启；不因安装验证工具而自动开启。桌面接入不可用时，设置仍能打开、编辑和导出。

## 进程接口与输入时序

- UI 经 Tauri 的窄接口访问 core；core 和 GNOME 扩展通过会话 D-Bus 交换请求、事件和能力状态。
- core 与 inputd 使用 Unix socket，保留 SO_PEERCRED、授权 UID、控制所有者及租期检查。root 组件不接收用户命令、文件操作、HTTP 或任意动作编排。
- 每个协议带版本、请求/事件标识、会话实例标识和明确结果；协商失败显示不兼容，不静默使用旧字段。桌面能力按动作/适配器报告，不以“已连接”推断所有功能可用。
- 窗口句柄由“扩展实例标识 + 稳定窗口标识”组成；Meta.Window 对象只留在扩展。窗口关闭或扩展重启后句柄失效，不改用当前焦点或同标题的新窗口。

鼠标主流程：

1. 右键开始，inputd 暂存右键与后续鼠标事件，通知 core。
2. 扩展获取起点坐标并命中窗口，固定窗口句柄、应用标识、标题和坐标；core 确认后 inputd 继续转发。
3. 应用禁用或功能暂停时，原输入透传。有效手势持续显示反馈，辅助键只参与该轨迹的匹配。
4. 松开后决定普通点击、取消或有效轨迹；点击重放，有效手势消耗右键。
5. core 识别与匹配规则，生成执行上下文并启动动作序列。

探针的握手和普通点击已有实机证据，但“冻结后续事件”不能代替核对前一批 uinput 移动已被 Shell 消费。正式接入须验证连续移动、负载下的起点快照顺序和握手延迟；不以终点窗口替代失败的起点绑定。

实际产品的轨迹长度使用桌面逻辑坐标；保留原始设备计数供诊断，不把探针 24 counts 阈值当作规格中的 12 像素。轨迹在屏幕逻辑坐标中重采样，保留比例、朝向和顺序；初始比较使用点序列距离与多样本最近匹配，按实际样本校准分数与阈值，不添加旋转不变性。

## 模型、配置与执行

正式模型包含：配置版本、设置、应用排除、手势模板/原始样本、手势规则、可复用动作、声明式步骤、文本替换规则。所有引用使用稳定标识，显示名称不充当主键。

- 类型覆盖文本、数字、布尔、列表、窗口与结构化数据，按动作定义声明输入/输出。变量、分支/循环作用域、有限重复和禁止递归按产品规格实现。
- 每次触发使用已保存配置的快照；编辑草稿不改变正在执行的序列。保存成功才更新活动配置，失败保留原文件和草稿。
- 配置位于 `$XDG_CONFIG_HOME/waystroke/config.json`；备份与运行记录位于 `$XDG_STATE_HOME/waystroke/`。采用结构校验和原子替换，导入/恢复的合并、冲突、备份规则沿用规格。
- core 是正式配置的唯一写入者，UI 提交草稿。浏览器设计稿的 localStorage 不自动当作正式配置导入；开发比对数据明确标为样本。
- 队列默认串行执行完整动作序列，避免两组输入/窗口动作交错；等待不阻塞输入采集或设置界面。队列设置在正式 UI 中明确展示，不将事件丢弃伪装成执行成功。
- 锁屏、退出、桌面连接断开或用户取消时停止剩余步骤，清理本程序按住的输入。目标失效按步骤策略报告失败；外部命令已产生的副作用不伪称可撤销。

动作以统一注册表连接参数、校验、输出字段和执行器；最终覆盖动作目录的 10 类、69 项。缺少宿主能力时返回具体原因，不用示例成功或空操作替代。命令、程序、文件、HTTP/D-Bus 动作均在普通用户进程运行。

## 文本替换适配

| 路径 | 正式接入基础 | 明确边界 |
| --- | --- | --- |
| 原生文本协议 | Shell surrounding text、提交/组合状态 | 保留确认键语义，按真实焦点/选择范围校验；其他应用密码字段继续排除 |
| XWayland GTK 等 AT-SPI 节点 | Text/EditableText、焦点、密码角色、文字事件 | 当前 GTK 已验证；不将所有可访问节点都视为可编辑 |
| 原生 Ptyxis/VTE 终端 | 输入法处理后的按键/提交、Space/Enter、一次提交删除字节与文字 | 用户允许普通和密码输入都替换；当前 canonical/Readline/getpass 通过，不保证 raw/TUI 自动解释删除 |
| Zsh 行编辑集成 | ZLE 直接修改编辑缓冲区 | 已验证的可选精确方案，不作为通用终端功能的强制依赖 |

匹配和应用范围统一由 core 定义，适配器只提供上下文与编辑能力。先满足全部规则触发模式，再补齐自身输入抑制和撤销；它们不是可省略的最终范围。

原生确认键到达 accelerator 前可能已被输入法消费；不能重放输入法已消费的确认。原生路径使用已处理按键接口，XWayland 使用经测试的虚拟键盘路径。当前 XWayland Rime 可见状态可作为额外阻止条件，不将候选可见等同所有输入法的组合状态；无法确认时报告适配限制。

终端缓存只保存匹配所需的短期内容，不落盘原始按键、密码或完整输入文本。焦点、光标/历史导航、粘贴及快捷键导致上下文不确定时清除匹配状态，不能用旧缓存猜测现有文档。删除字节及控制语义属于终端适配，不把 VTE 的 DEL 路径直接复制到所有应用。

## 界面实现约束

- 8 个主页面、全宽动作编排、配置草稿、弹窗和关键状态按原型复刻；保留规则编辑连续滚动、固定保存栏和编排三栏。
- 窗口外评审工具和“模拟环境”不进入正式应用；示例记录只用于开发比对，不进入真实运行记录。
- 正式窗口保留设计稿的边框与客户区。原型已补齐最小化、最大化、关闭与未保存确认，拖动区域已标注；Phase 1 绑定 Tauri 窗口 API 并核对实际缩放/渲染，不把浏览器中隐藏预览窗口的交互当成原生实现。
- 连接、空状态、错误、权限和不支持能力使用真实数据。相关技术边界的解释放在已有运行状态/设置界面，普通操作流程不展示内部协议。
- 69 项表单按统一动作定义生成；UI 不能出现有表单却无执行器的“可用”动作。开发阶段未完成项显式标明，正式发布逐项核对覆盖。

## 执行方式与完成判定

本文件是实施顺序与验收清单，不另建多份重复计划。开始任务时改为进行中，通过后记录具体代码入口和验证结果；失败或未实现保留待办，不能仅勾选页面截图。阶段之间可以提前实现依赖，但不得将本阶段未完成项从最终范围中删除。

- 功能依据以产品规格和动作目录为准；视觉与操作流程以当前 `design/` 为准。出现矛盾时记录并修正，不能悄悄选择较少的范围。
- 尚未完成的开发界面不得把动作显示为可执行成功；最终发布不得残留“待实现”、样本运行记录或没有后端的控件。
- 不预估未经实际构建支持的工期；按下面依赖推进，每次交付可运行的真实增量。第一阶段是工程入口，不是完整产品。
- 自动化检查优先覆盖真实风险与代表性分支；69 项动作逐项需要执行证据，但不要求为每个参数组合建立测试套件。
- 需要管理员密码、真实鼠标操作或用户桌面确认时才请求用户协助。可用独立 GNOME、固定测试文件和测试应用完成的工作持续推进。

## 正式工程布局

```text
Cargo.toml / Cargo.lock       Rust workspace 与精确依赖
apps/desktop/                Tauri 2、TypeScript、Vite；保留设计稿 DOM/CSS
  src/                       页面、草稿、动作表单、运行订阅、画布
  src-tauri/                 窗口控制、文件对话框、core 客户端
crates/model/                配置、引用、类型、动作注册表、语义校验
crates/protocol/             IPC 请求/事件/能力/错误；生成前端类型
crates/core/                 配置仓库、识别/匹配、编排、适配器、状态
crates/inputd/               evdev/uinput、设备发现、租期、事件状态机
extension/                   GNOME 50.5 窗口、输入、IME、反馈、锁屏
packaging/                   RPM、systemd、polkit、桌面入口、安装卸载
scripts/                     开发构建、独立桌面验证与 UI 比对入口
fixtures/                    固定手势、动作、配置与 UI 评审数据，仅测试使用
design/                      原始视觉和交互基线，保留作对照
probes/                      既有验证工具，正式运行不依赖它们
docs/                        产品、动作、证据和本计划
```

先落地这些明确职责，不为将来可能出现的需求增加框架层。Rust 模型生成 TypeScript 类型；前端不要维护另一套独立协议/动作枚举。动作定义生成表单描述，特殊键值表、坐标、D-Bus 参数编辑器沿用原型结构。

## 模型与接口落地合同

### 配置和草稿

初版配置头采用 `format: "waystroke"`、`schemaVersion: 1`。运行实例的 `revision` 与保存时间用于并发校验，不作为跨设备身份。核心对象如下，字段的 Rust/TypeScript 声明在 A02 完成，后续任务依此实现。

| 对象 | 必备数据与约束 |
| --- | --- |
| Settings | 手势启停、鼠标稳定身份、轨迹/反馈开关与颜色、阈值、最小长度、停留取消、自动启动、文本开关、终端开关；值域沿用 HTML |
| Application / Exclusion | 应用 ID、显示名称；手势与文本各自排除；手动应用与桌面应用可并存 |
| GestureTemplate / Sample | 稳定 ID、名称、主样本 ID、样本 ID 和原始逻辑坐标点；归一化数据可重建，不取代原始轨迹 |
| GestureRule | 稳定 ID、名称、启用、模板引用、辅助键集合、应用/标题条件、步骤树；全局范围不伪造应用 ID |
| Workflow | 稳定 ID、名称、说明、输入参数/默认值、返回字段、步骤树；参数和返回字段均有稳定 ID |
| Step | 稳定 ID、动作 ID、启用、参数、输出绑定、失败策略、超时、children/otherwise；嵌套和引用按类型校验 |
| Value / Binding | 文本、数字、布尔、列表、窗口、结构化数据；字面量、变量/字段引用和文本插值分开存储，不解析用户代码 |
| TextRule | 稳定 ID、关键词、替换内容、启用、作用范围、触发模式、大小写/前边界、确认键保留选项 |
| Execution / StepResult | 执行 ID、配置版本快照、起点上下文、步骤 ID、状态/时间/原因、可显示的结果摘要；与导出配置分离 |

变量名只用于显示和编辑；绑定按稳定 ID 维护。重命名不得破坏引用，复制步骤/动作重新生成局部 ID 并重映射内部引用。输出提供者必须在当前可见作用域的此前启用步骤中；分支/循环局部值不泄漏。已关闭窗口的值保持失效身份，不能按标题重新查找冒充原对象。

初次正式配置使用空规则、空模板、空动作和空文本列表，显示设计稿空状态，不默默安装示例自动化。设置采用设计稿默认值：轨迹与反馈开启、颜色 `#6262cf`、阈值 82%、歧义差 5 个百分点、最短 12 逻辑像素、停留 1200 毫秒、文本与终端路径开启。自动启动控件初值沿用设计稿的开启；**仅在用户完成初次设置后应用该偏好**，安装包不得自行接管输入或启用登录启动。

### UI → core

Tauri 仅桥接下列命令族，操作返回类型化结果，不暴露任意 root 调用。请求带 `requestId`；写入带 `expectedRevision`，冲突保留草稿并提示重新加载。

| 命令族 | 具体操作 | 返回与副作用 |
| --- | --- | --- |
| 配置 | get_config / validate_document / commit_document / delete_entity / update_settings | 配置与 revision、引用来源、定位到字段的错误；保存成功后才切换活动配置 |
| 桌面 | get_status / list_devices / select_device / list_applications / pick_window / reconnect | 真实能力/设备/应用/起点选窗结果；设备切换先释放旧设备 |
| 手势 | recognize_stroke / begin_recording / end_recording | 候选分数、规则依据、取消/录制结果；测试不修改样本，不自动执行 |
| 执行 | preview_execution / start_execution / cancel_execution / stop_all / get_execution | 预览仅解析上下文；显式执行返回执行 ID，结果由事件更新 |
| 文本 | test_text_rule / get_text_context / undo_last_expansion | 页内测试不操作其他窗口；实际撤销须验证焦点、范围和版本 |
| 配置文件 | inspect_import / apply_import / export_config / create_backup / list_backups / restore_backup / delete_backup / export_backup | 真文件、真实摘要和可恢复备份；检查与应用分离，确认前不写正式配置 |
| 生命周期 | complete_setup / set_autostart / export_diagnostics / quit | 安装/授权按既有向导；退出取消执行、释放设备并停止会话组件 |

订阅事件：`config_changed`、`capability_changed`、`device_changed`、`gesture_state`、`recognition_result`、`execution_changed`、`queue_changed`、`text_context_changed`、`connection_changed`。连接建立先取完整快照再处理后续事件；断开显示真实失败，重连重新取快照，不把过期事件恢复为当前状态。

共同错误至少区分校验失败、配置冲突、权限不足、能力缺失、目标失效、超时、取消和 I/O 失败。错误包含可定位的实体/步骤/字段及可读原因；异常必须可诊断，不能统一变成成功 toast。

### core ↔ GNOME 扩展与 inputd

- 会话 D-Bus 名称采用 `io.github.waystroke.Core` 和 `io.github.waystroke.Gnome`，接口版本从 1 起。扩展提供 Hello/Capabilities、起点快照、选窗、窗口/工作区动作、输入/剪贴板/系统动作、文本上下文和编辑、锁屏事件。普通配置编辑不依赖扩展在线。接口仅接受同一用户会话的客户端，校验调用身份；Tauri权限只授予所需本地命令，不开放远程内容调用。
- 起点快照包含序列号、单调时间、逻辑坐标、窗口句柄、应用/标题、工作区/显示器、是否锁屏。请求与响应匹配本次手势及扩展实例，超时不绑定后来的焦点。
- inputd 使用 `/run/waystroke/` 下受控 Unix socket；消息包含协议版本、控制租期、手势序列、设备身份、事件时间。只提供设备列表、接管/释放、开始握手、原始事件转发和健康状态，不执行用户动作。
- 延续已验证探针的默认控制租期 3 秒、起点握手上限 250 毫秒；正式心跳与事件传输采用异步读写，禁止沿用旧客户端输出轮询导致的延迟。超时期间未形成有效手势的原始点击按状态机透传，过期响应丢弃。
- 设备按物理身份/udev 属性识别，不保存易变化的 eventN 为唯一配置；不猜选另一只鼠标。设备拔出、锁屏、租期失效、服务退出必须销毁接管并释放合成按键。只有向导授权的UID可以成为控制者，禁止用可写请求自行添加授权用户。
- 实际桌面位置由 Shell 上报。正式接入必须解决 uinput 事件与 Shell 消费先后的起点顺序；不把设备计数直接积分当作最终屏幕逻辑坐标。若起点时序验证不通过，B02 未完成，不能以“多数情况正确”放行。

### 执行与文本生命周期

执行状态：排队 → 执行中 → 成功 / 失败 / 取消；步骤还包括跳过和等待。序列按 FIFO 串行，停止全部取消当前及清空队列；锁屏/断连取消且解锁不恢复。配置保存不改已触发快照。动作显式暂停后续触发不等于取消当前任务，停止由独立操作控制。

每个执行器处理取消与超时；释放本程序按下的键/鼠标、恢复本程序创建的临时剪贴板、关闭等待与对话框。命令异步启动返回 PID，不假装已经成功结束；等待型命令取消会终止本程序启动的进程组，已脱离等待的程序不因“停止动作”被随意杀死。用户明确要求发送信号的动作单独实现。

`WindowResult` 使用窗口句柄；`CommandResult` 使用 pid、exitCode、stdout、stderr；`HttpResult` 使用 status、headers、body；文件目录返回类型化列表；询问/输入返回确认状态及值。明确取消不得返回一个看似有效的空值。扩展disable必须移除信号/accelerator/overlay，并恢复本程序包装的输入法函数；不能影响其他扩展或留下重复监听。敏感输出只在需要的内存变量/界面中使用，运行记录不自动落盘命令输出、剪贴板内容、替换文本或终端输入。

文本上下文携带焦点身份、适配器、文本版本、光标/选区、组合状态和输入用途。一次替换与撤销按这些数据校验；不确定则清除上下文并显示限制，不猜删字符。自身提交带来源标识，抑制仅限本次生成内容，不长时间屏蔽用户输入。终端允许密码输入，但锁屏仍不采集。原生/AT-SPI 路径执行后校验编辑结果；终端原始模式没有可靠确认机制，运行状态必须保留“部分支持”的实际边界。

D-Bus 参数初版覆盖设计稿提供的 `s/i/d/b/as`，按类型生成签名，返回值解码为结构化值；其他签名明确报不支持，不做猜测。它不代表删除 D-Bus 动作范围；以后新增类型是明确扩展，不在初版悄悄接受后丢弃。

## UI 一比一复刻与功能对应

### 视觉基线

A01 固定当前 `design/` 的文件校验值与代表性截图，防止开发过程中基线被无意改变。正式前端保留窗口客户区 DOM 分区、类名和 CSS 数值，迁移脚本和数据绑定，不重新设计布局、不替换为默认 Tauri/GTK 控件风格。

- 对齐窗口边框、标题栏、侧栏、字体字号/行高、紫色、间距、圆角、阴影、图标、输入控件、按钮、滚动容器、弹窗、空态、错误和反馈。
- 规则编辑继续连续滚动，顶部编辑头和底部保存栏位置一致；编排保留步骤树、参数、变量/接口三栏及嵌套层级。
- 窗口外背景、评审工具、恢复预览按钮、浏览器模拟最大化/关闭不进入产品。标题栏客户区与边框照原型，真实拖动/缩放/最小化/最大化/关闭绑定 Tauri API。
- 静态文案照设计稿；版本号、设备、应用、状态、记录和分数绑定真实值；“当前为配置预览”“模拟选取窗口”等原型说明替换为对应的正式语义，保留原有文案区域，不改变布局。
- 首先记录原型默认客户区尺寸，再以相同内容区域、缩放和数据比对 Chromium 原型与 WebKitGTK；另验设计稿已有窄窗口、最大化和长内容滚动。字体/抗锯齿的引擎差异单独核对，不能借此放宽结构、颜色或间距。
- 发现 WebKitGTK 缺少某 API 时用等价实现保留效果与交互。任何确实需要改变设计的差异先形成具体对比；不能以实现方便单方面改版。

### 页面交付矩阵

每行都必须同时满足视觉和功能验收。矩阵的依赖说明真实闭环完成时间，不允许 Phase 1 展示页面后将其标为最终完成。

| 页面 / 视图 | 原型来源 | 正式交付内容 | 主要依赖 / 完成证据 |
| --- | --- | --- | --- |
| 手势规则 | app.js、gestures.js | 搜索/范围筛选、启停、新建/复制/删除、草稿；模板、辅助键、选窗/手动应用、标题条件、简单动作/全宽编排；共享样本确认、冲突与必填反馈、固定保存栏 | A02–04、B02–04、C01–05；保存后真实触发，重启仍有效；取消不改活动配置 |
| 手势模板 | gestures.js | 列表、主样本/其他样本、重录/删除、试画分数、共享引用与删除限制；保留真实轨迹形状 | B03–04；两条规则共享后修改同步，试画不污染样本，引用不能悬空 |
| 可复用动作 | composer.js | 搜索、新建/复制/删除、来源引用、参数/返回接口、进入编排、从规则另存及改为调用 | A02、C01–05；修改同步影响调用、复制独立、被引用删除及递归有定位提示 |
| 全宽动作编排 | composer.js、actions.js、form-details.js | 全部动作选择/搜索、树排序/复制/嵌套/启停、动态参数、失败/超时、变量插入、键值表、坐标、类型化 D-Bus、输入与返回接口；应用回规则/取消/独立保存 | C01–05；保存后的结构真正执行，类型/作用域错误阻止执行并定位，非仅存字符串 |
| 文本替换 | app.js | CRUD、启停、编辑弹窗、触发模式、范围/边界/大小写/确认保留、页内测试、接入范围链接 | D01–04；实际编辑器与终端触发、IME不误替换、密码策略与撤销正确；页内测试不等于全局接入 |
| 手势测试 | app.js | 自由绘制、真实识别候选/分值、起点窗口与规则优先级依据、将执行摘要、显式执行及详情 | B03–04、C02–05；默认仅预览，点击执行才产生动作，无固定匹配结果 |
| 运行状态 | runtime.js | 组件/手势/文本独立状态、能力说明、当前任务/队列/停止、最近结果/失败/执行详情、重新连接、诊断、接入入口和退出 | A04、B01–02、C02、D04、F01；连接失败/授权/锁屏均来自真实组件，最近结果没有样本混入 |
| 配置与备份 | configuration.js | 实际文件选择/导出/摘要、合并/替换确认、自动备份、最近5份、本地恢复/导出/删除、版本/引用错误 | E01–02；另一个配置真实生效、失败原配置不变，重启看到同一备份列表 |
| 设置 | app.js、runtime.js | 实际设备选择、轨迹/颜色/阈值/取消设置、串行策略、自动启动、文本/终端开关、应用排除与选窗 | A03、B01–04、D04、F01；实际行为随设置变化，自动启动项控制真实会话入口，权限不足不假报成功 |
| 初次设置及标题栏 | runtime.js、window.js、index.html | 欢迎/接入/使用三步、扩展连接/服务授权/设备、真实窗口控制、草稿关闭确认、后台继续与退出区别 | A01、A04、B01、F01；首次无授权仍可编辑、拒绝授权可重试；关闭窗口不退出core，退出释放输入 |

弹窗逐一迁移：确认更改、通用消息、初次设置、执行详情、文本规则、另存可复用动作、变量插入、窗口选取、动作选择。保持焦点、Esc/取消、关闭按钮、遮罩、滚动和错误位置。原型选窗列表改为真实选取/结果，不能保留“Probe A/B”作为用户窗口。消息/询问与请求用户输入动作在设置窗口关闭时也必须能唤起真实对话框，不能等待永远不会打开的 UI。

统一状态验收：默认有数据、初次空态、搜索无结果、表单错误、未保存离开/关闭、服务缺失、鼠标待授权、连接失败、版本不支持、锁屏、文本能力不足、执行中/排队/失败/取消、导入失败。开发夹具可重现画面，但产品运行只能由实际事件进入状态。

## 分阶段可执行任务

下列任务的完成状态见文末实施记录。依赖用任务编号表示；“通过条件”是停止扩大验证和进入后续任务的依据，不再为通过的阶段反复补低收益检查。

### A：工程、真实配置与桌面窗口

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| A01 | 无 | 建 workspace、Tauri/Vite/TypeScript、锁文件、统一构建入口；迁移原型 CSS/DOM，去掉窗口外评审；接真实窗口控制与关闭事件；保存 UI 基线 | 可构建启动，Shell识别原生Wayland客户端；八页/编排/弹窗视觉与原型一致，窗口缩放/拖动正常；此时未接功能不算完成 |
| A02 | A01 | model：上述配置和类型、69动作注册信息、稳定引用与步骤AST、前端类型生成；validate_document 语义校验 | 正式模型能无损保存自由轨迹和全部参数；未知动作/悬空引用/递归/错误类型被定位；复制与重命名不破引用 |
| A03 | A02 | core/config：唯一写者、revision、XDG路径、原子保存；前端八页CRUD、草稿/计数/筛选统一接入，移除localStorage正式依赖 | 实际创建规则/模板/动作/文本并重启恢复；草稿取消不落盘、写入失败保留旧配置；初次空态有效 |
| A04 | A03 | core单实例、会话D-Bus服务、Tauri客户端与事件订阅；重新打开已有窗口；断连/退出状态和错误映射 | 关闭UI后台存活，重开取真实配置；重复启动不产生两个core；断连能编辑草稿且不假保存；真实退出被确认 |

A 阶段交付是可运行的编辑与持久化工程，桌面动作尚未完成，不得称为可用手势产品。

### B：真实鼠标手势闭环

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| B01 | A04 | inputd：Rust移植已验证设备筛选/转发/接管/租期，普通用户控制协议、真实发现/选择；GNOME扩展握手、锁屏事件；先提供开发安装入口 | G304普通右键/移动正常，辅助键正确；不接管键盘/触摸板；拔出/控制断开/锁屏释放；event编号变化仍选对设备 |
| B02 | B01 | 扩展+core：起点冻结时序、窗口身份/应用标识/逻辑坐标、跨窗和多屏；输入状态机与录制会话互斥 | A起点且B焦点/终点始终绑定A；窗口消失不转给B；负载/连续移动起点正确；录制期间不会同时触发已保存规则 |
| B03 | B02、A02 | core/gesture：64点弧长重采样、统一尺度/平移、带宽 DTW 对齐、保留比例朝向顺序、多样本；阈值/歧义；规则应用/标题优先级、辅助集合与排除 | 固定轨迹验证尺度平移一致、反向/旋转保持区别；代表性真人样本评估；停用专属回退全局、歧义不执行 |
| B04 | B03、A03 | 模板/规则/测试页面接真实识别；扩展轨迹overlay和反馈、最短/停留/Esc取消；基本执行器快捷键/启动/窗口操作联通 | 录制→保存→重启→跨窗识别→实际动作闭环；12逻辑像素规则有效；辅助不能独立触发；点击透传、有效未识别/取消不出菜单 |

B 阶段至少用一个快捷键、一个程序启动和一个窗口动作形成完整实机闭环。测量松键→识别/入队/开始执行链路，单列排队与握手时间；修复旧探针约0.5秒输出等待，不能把轮询延迟带入正式产品。数值记录为实测，不能提前宣称未取得的性能保证。

### C：声明式编排与全部 69 项动作

**状态：已完成。** 用户明确确认“测试环境验证通过即代表通过”，阶段 C 不再要求主桌面验证。C01–C05 与 69 项动作的验收证据见下方索引及文末完成记录；硬件/服务限制按实际能力明确报告。

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| C01 | A02–03 | 编排编辑器接正式模型：排序/复制/嵌套/启停、输入输出接口、动态参数、引用/变量选择、局部作用域与类型提示 | 编辑和重启保留结构，非法变量/循环退出/递归定位；规则另存为动作及改为引用真实完成 |
| C02 | A04、C01 | core/execution：快照、FIFO、分支/等待/重复/遍历、break/continue/stop/call、类型化变量/输出、超时/失败继续/取消；真实运行事件和详情 | 多步与嵌套真实执行；等待不阻塞界面/输入；停止清队列/释放按键；失败/继续/取消状态和详情一致 |
| C03 | C02 | core动作执行器：变量/数据、应用/命令、文件、HTTP、D-Bus、WayStroke控制；使用临时目录和本机fixture服务 | 下方对应动作逐项执行；结果可被后续步骤引用，命令直接/Shell及异步/等待正确；文件失败和HTTP超时不伪造成功 |
| C04 | B04、C02 | extension桌面执行器：完整键鼠、剪贴板、窗口/工作区、应用目标与选窗、显示桌面恢复 | 每个目标显式校验；复制选中文本不读旧剪贴板；临时粘贴恢复策略验证；多屏/窗口状态和所有操作枚举正确 |
| C05 | C03–04 | GNOME/system桥接：音量/静音、亮度、MPRIS、截图、通知、询问/输入、会话/系统设置；动作能力注册汇总与69项核对 | 每项有真实执行结果或基于硬件/服务的明确能力限制；实际支持项执行成功、缺能力项不成功；无UI壳时对话框可用 |

C04/C05 包含动作目录中尚未完成的系统接入验证，不能把核心输入验证完成误当作69项已经可行。实现任务内先做最小独立接入核对，再实现正式执行器；若已确认功能无法按原接口实现，应找到可行替代并保持同一产品行为，确实受系统限制时记录具体证据，不能悄悄删除。

一次代表性编排验收：读剪贴板→处理文本→HTTP→按状态分支→循环文件列表→通知；再验等待窗口出现→显式改目标→输入、可复用参数/返回、失败继续、用户取消。破坏性操作仅对固定测试对象执行；注销/挂起不自动在用户主会话测试。

### D：真实文本替换

**状态：已完成（2026-10-15）。** 扩展程序验收仅在 mutter-devkit 独立 GNOME 环境进行；测试环境通过即视为通过，不要求主桌面重复测试。

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| D01 | A02–04、B02 | core/text：规则匹配、逐条四种触发、关键词边界/大小写/专属覆盖、多行、确认保留/吞掉；页内测试与全局共享匹配逻辑 | 应用专属触发覆盖全局、停用回退；立即模式不假设后边界；编辑弹窗和页内测试结果真实 |
| D02 | D01 | extension原生周围文本/IME、Rust AT-SPI焦点/角色/Text/EditableText、确认键协作；原生与XWayland各自重放路径 | GTK/Firefox/Electron/XWaylandGTK实际替换，中文多行/组合确认不误删；非终端密码跳过，旧焦点操作取消 |
| D03 | D01–02 | 通用终端适配：IME后按键/提交跟踪，短期缓冲，一次提交删除+替换，Space/Enter、立即模式、确认吞掉；导航/快捷键/粘贴清上下文 | 当前Ptyxis/VTE canonical、Readline、getpass和Rime通过；终端密码允许；无Shell插件强依赖；raw/TUI限制如实呈现 |
| D04 | D02–03、C02 | 自身输入抑制、刚发生替换的撤销；全局/终端开关、应用排除、状态订阅、锁屏/断连清理 | 生成内容不递归；撤销仅当前焦点可确认的最近替换，导航后不误删；开关即时生效，鼠标未授权不阻止文本 |

撤销使用文本适配器的“最近替换”记录；普通编辑器在可验证的紧邻状态下截获 Ctrl+Z 恢复关键词并保留原确认语义，否则交还应用原生撤销。终端采用仅紧邻可验证状态的撤销，不宣称具备文档级撤销；在没有可靠范围时不注入猜测删除。快捷键处理必须不抢输入法组合确认，具体实机行为在 D04 验收并记入用户帮助。

D 阶段实施记录（历史过程，2026-10-14 起）：

- D01：新增 `crates/core/src/text.rs` 正式共享匹配器及 `TestTextRule` D-Bus/Tauri 接口；四种触发、启用专属规则跨触发方式覆盖全局、停用回退、前边界、大小写、多行、确认保留/吞掉，以及开关/应用排除/组合/密码策略由 core 统一处理。协议文本偏移使用 Unicode scalar，UI 在应用时转换为 DOM 的 UTF-16 偏移。
- 页内试输入已移除独立 JS 匹配算法和固定示例说明，使用已保存的正式配置；异步结果校验输入、光标、应用和组合状态，粘贴/删除不触发，自身生成内容不再次匹配。页内撤销在紧邻未变化状态恢复原输入，导航后失效；这不代表 D04 全局撤销已完成。
- 已验证：`cargo test -p waystroke-core text::tests`（2 个代表性测试）、`cargo build -p waystroke-core --offline`、`python3 scripts/check-core.py`（新增实际文本 RPC、多行、Unicode 边界、组合、普通密码跳过/终端密码允许检查）、`npm run check --prefix apps/desktop`、`npm run web:build --prefix apps/desktop` 均通过。页内原生窗口交互验收仍待完成；后续原生 GTK 增量见下一条。阶段 D 不算完成。

- D02/D04 原生增量：新增 `extension/text.js`，直接连接真实 `surrounding-text-set` 与 IME 后 `notify_key_event`；原生确认键在后处理入口消费并用 `forward_key` 保留原语义，不能依赖原生通知后并未触发的 Shell accelerator。替换前核对焦点/窗口/文本/选区/请求代次，替换后以客户端周围文本确认结果。提供紧邻 Ctrl+Z 撤销、导航失效、生成文本抑制、密码与排除直接透传、配置开关/后台身份订阅，以及 disable 信号/定时器/accelerator/输入法包装清理。开发安装与隔离检查复制新模块，不更新主会话。
- 原生 GTK 隔离验收通过：`python3 scripts/check-gnome.py --devkit --phase-d-text`；证据 `fixtures/phase-d/native-gtk.json`、受测源码哈希 `native-source.json`。空格/Enter、立即、确认保留/吞掉、紧邻撤销/原空格保留、导航失效、动作生成文本抑制与替换不递归、普通密码跳过、应用排除及开关透传均通过；鼠标未授权。测试夹具状态改为原子更新，修复读取半写 JSON 的竞态。仍待 Firefox/Electron、中文多行/IME、旧焦点专项、Rust AT-SPI/XWayland、通用终端、锁屏/断连专项与真实运行状态页面，D02–D04 不标记完成。

- D03/D04 终端增量：新增 `extension/terminal.js`，复用 core 匹配器；IME 后按键/真实提交跟踪、关键词长度决定的短尾部、单次 DEL+替换+确认提交、Space/Enter/立即与确认吞掉、紧邻且未提交换行的撤销、导航/快捷键/焦点清理、终端开关/应用排除与生成输入抑制已接入。事件明确为已提交，保留 canonical/Readline/getpass 支持与 raw/TUI 无可靠文档校验的边界；前边界未知不按空文档猜测。没有 Shell 插件依赖。
- `python3 scripts/check-gnome.py --devkit --phase-d-terminal` 通过；`fixtures/phase-d/terminal-vte.json` 与 `terminal-source.json` 保存结果和源码哈希。真实 Ptyxis/VTE 的 canonical、Readline、getpass（密码仅记录固定夹具结果的长度/匹配布尔值）、四种触发代表分支、Space/Enter 吞掉、紧邻撤销、导航、跨焦点前边界保护、终端关闭/应用排除/动作生成文本、Rime 组合提交与 raw 字节均验证。短时间连续键入暴露的吞 Space 根因已修复为 IME 后排队；原生立即模式等待实际客户端对应文本更新，Shell 确认 accelerator 限制在 XWayland 窗口，避免干扰原生透传。粘贴失效、锁屏/断连专项、浏览器/原生多行/IME、Rust AT-SPI/XWayland 与运行状态界面仍待完成，阶段 D 保持进行中。

- D02 AT-SPI 确认增量：`crates/core/src/atspi.rs` 使用 zbus 连接用户 AT-SPI bus，按辅助功能连接的真实 PID 与 Shell 稳定窗口句柄绑定，过滤密码/终端子树、焦点/可编辑状态、Text/EditableText 接口及选择范围；编辑前后检验文字、光标与桌面代次。`ExpandAccessibleText` 同 UID 授权，400 ms 操作上限，失败不伪称成功。扩展新增 `textGuard` 与 IBus panel 组合/候选状态监控；XWayland 确认 accelerator 调用 Rust 编辑器后才用独立虚拟键路径重放。
- `python3 scripts/check-gnome.py --devkit --phase-d-atspi` 通过；`fixtures/phase-d/atspi-xwayland.json`/`atspi-source.json` 保存实际结果与源码哈希。XWayland GTK 的正式 RPC、确认空格/Enter、activate 得到替换后的输入、中文 UTF-8 字节长度与 Unicode 光标、密码字段跳过、旧焦点拒绝均通过。私有测试显式启动 AT-SPI bus/registry；曾发生的确认键测试失败来自 Shell 尚在启动动画中，现等待实际 NORMAL 状态。Rust 构建、既有匹配测试及前端类型检查通过。AT-SPI 的立即事件监听/紧邻撤销/自身输入来源、XWayland Rime、多行与浏览器、粘贴与生命周期专项、运行状态和原生页内交互尚待完成；阶段 D 不完成。

- D04 AT-SPI 撤销增量：正式 `UndoAccessibleText`/`ClearAccessibleText`、一次替换的内存令牌、再次校验紧邻范围与光标、确认空格语义保留、光标/焦点真实事件失效及编辑串行锁已实现。Shell `captured-event` 实测不能收到普通 XWayland 应用按键，已删除无效路径；撤销失效由 AT-SPI `TextCaretMoved`/`StateChanged:focused` 负责。来源连接的消息序号排除编辑完成前的旧事件，导航往返不重新激活旧记录。解析当前 GTK 的 `(siiva{sv})` 实际结构，同时兼容旧结构。
- 本轮 mutter-devkit 验收：`--phase-d-atspi` 的紧邻 Ctrl+Z、确认空格保留与导航往返失效通过，正常确认/Unicode/密码/旧窗口焦点检查仍通过；`--phase-d-text` 原生 GTK 回归通过。证据和源码哈希已更新。AT-SPI 部分编辑错误带阶段信息，焦点变化/超时/部分修改后停止确认键重放，故障专项仍待生命周期测试；停用后的输入法包装在其他扩展持有旧包装时直接透传。Rust 构建与前端类型检查通过。已核对真实 DeviceEventController 接口并归档 XML，但立即模式输入来源监听仍未实施；自身生成/粘贴与原生撤销来源抑制、XWayland Rime、窗口内换焦点竞态、浏览器/多行、生命周期与运行状态等保持待办，阶段 D 不标记完成。

- D02/D04 AT-SPI 立即模式增量：新增 `crates/core/src/atspi_input.rs`，以 GNOME 立即规则末字符 accelerator 建立真实输入起点，再等待对应 AT-SPI 提交；绑定原节点身份，不把后来焦点替代原编辑区域。仅保留一次意图，匹配复用 core；本程序虚拟键盘校准/过滤避免重放与动作生成再次触发，保留实际 Shift 符号。提供真实来源监听状态/错误及计数 API，UI 状态订阅仍待后续统一接入。DeviceEventController 的注册返回值与监听表不足以证明键来源：全局和工具包模式均未收到回调，已移除不可用实验路径，采用已实际证明的 GNOME/AT-SPI 协作路径。
- `--devkit --phase-d-atspi` 最新检查通过真实立即替换、立即撤销不再触发、动作输入抑制、Ctrl+V 粘贴不触发、Shift/大小写匹配和生成内容不递归；确认、Unicode、密码及旧焦点检查仍通过。`--phase-d-text` 原生 GTK 回归通过；Rust 构建、JS 语法及前端类型检查通过。结果与源码哈希已归档。XWayland 中文 IME 提交/立即模式、浏览器/多行、窗口内换焦点、终端粘贴与生命周期、运行状态与页内原生交互仍待完成，阶段 D 保持进行中。

Zsh ZLE 保留为已验证的可选适配基础，不作为本次通用终端功能前提，也不以只实现Zsh替代D03。首版不新增独立Zsh插件分发需求。

- D04 状态与 UI 增量：`RuntimeInfo.text` 由正式扩展实时提供当前应用/适配器、启用与终端开关、组合/密码/排除/锁屏/不可用状态及撤销可用性；`lastTextResult` 仅保存结果、原因、规则 ID 和时间，不保存输入或替换内容。运行状态页面订阅真实状态，移除文本静态样本；鼠标未选定、未接管时文本仍可用。`python3 scripts/check-ui.py --devkit --phase-d` 通过页内共享匹配器的中文多行与撤销、真实 GTK 替换、最近结果订阅、密码跳过及关闭状态；证据 `fixtures/phase-d/ui-native.json`、`ui-source.json`。测试等待 Shell 启动与正常模式，再建立真实字段输入上下文；GTK 原有 devkit 回归通过。
- D02 浏览器增量：`python3 scripts/check-gnome.py --devkit --phase-d-browser` 完整通过 Firefox 中文多行/确认保留、可验证单行紧邻撤销、立即替换、密码字段、同窗 textarea → contenteditable，以及真实 Rime 预编辑保护、消费确认键、中文确认和中文立即提交；证据 `fixtures/phase-d/firefox-native.json`、`firefox-source.json`。Firefox 多行可能只回报当前段落，现核对对应段落及光标，并明确记录范围受限的已提交；完整范围不可验证时交还应用原生撤销。原生空格与替换一次提交，IME 提交等待组合结束与文本回报，删除/快捷键后不从旧全文预测后续输入；重复或过期配置版本不再重置当前输入。
- 输入队列根因修复：Clutter IM API 先排入事件队列，Mutter 随后以 idle 发送 text-input-v3 `done`；同帧多次 `commit_string` 可覆盖前一次提交。队列现等 `after-update` 再以较低优先级继续，不用固定延迟；已处理按键的释放及时传递，确认超时不丢弃同焦点后续输入。`request_surrounding` 只读取合成器缓存，不能强制客户端刷新，实验调用已移除。依据 [Mutter 50.5 text-input](https://raw.githubusercontent.com/GNOME/mutter/50.5/src/wayland/meta-wayland-text-input.c) 与 [Clutter IM API](https://raw.githubusercontent.com/GNOME/mutter/50.5/clutter/clutter/clutter-input-method.c)。移除临时诊断后，原始快速输入节奏的 18 项终端回归全部通过，证据与哈希已更新；GTK 回归通过。Electron 同一完整浏览器分支亦通过：`--devkit --phase-d-browser --electron`，证据 `electron-native.json`、`electron-source.json`。临时 Electron 运行时不修改 Code 安装。XWayland IME、窗口内焦点竞态专项、终端粘贴与生命周期仍待完成，阶段 D 不标记完成。

- D04 生命周期增量：终端 IME 缓冲在应用排除、禁用或输入法未连接时不再积累；用途/隐私判断使用 Clutter 保留的公开属性，避免 IBus 清除私有缓存后丢失密码标志。core 断连以新 owner/连接代次作边界，丢弃旧状态通知与旧配置回复。AT-SPI 关闭的连接不再复用，监听错误定时重连；注册服务换 owner 时清空旧撤销与监听，并重新注册。GTK 在注册服务重启后可能不重新登记应用，core 保留已验证的应用根引用，每次重新核对存活总线身份、实际 PID、焦点/角色/编辑接口，不缓存文本。`--devkit --phase-d-text --lifecycle` 与 `--devkit --phase-d-atspi --lifecycle` 通过真实进程停止/恢复、密码保护、锁屏禁用/解锁清理及同一 GTK 应用的注册服务重启后替换；证据 `lifecycle-native.json`、`lifecycle-atspi.json` 与对应源码记录。
- 锁屏事件两个入口均同步文本暂停与撤销不可用；扩展随真实锁屏被禁用时，UI 仍明确显示锁屏暂停。前端配置通知只应用更高版本，防止迟到的旧通知重绘并清空页内输入。最新 `--devkit --phase-d` UI 检查通过实际锁屏/解锁、页内共享匹配与状态订阅。新增真实中键粘贴用例尚失败，`terminal-paste-pending.json` 保留未完成证据；未收到客户端鼠标事件的 Clutter 过滤器实验已移除，不将其作为已实现的清理路径。XWayland 中文 IME、焦点竞态专项与终端粘贴仍待完成，阶段 D 保持进行中。

- D03 粘贴收尾（2026-10-15）：生产原生组件观察选区 source 的传输请求，不读取内容、不改变所有权；已有 source 与 owner 更新均覆盖，停用恢复 vfunc。终端无观察组件时明确不可用并透传。最新 devkit 20 项终端验收通过，两个中键粘贴用例覆盖原生 source 和实际 GTK Wayland 外部主选区，VTE 真正读入 `X` 后缓存失效，后续空格保持 `abcX `，不误删旧关键词。GNOME 50 默认关闭中键粘贴，夹具只在私有会话启用；证据 `terminal-vte.json`/`terminal-source.json` 已更新。原生库 MIME 原样读取与观察器停用验证通过。XWayland 中文 IME、焦点竞态专项与最终帮助审计仍待完成，阶段 D 保持进行中。

- D02 XWayland 中文 IME 收尾（2026-10-15）：`--devkit --phase-d-atspi --ime --lifecycle` 完整分支通过真实 GTK/Rime 的组合保护、`你哈哦` 提交、确认吞掉与中文立即替换，同时保留旧 ASCII/Shift/撤销/导航/生成及粘贴抑制与注册服务恢复。组合确认改为独立 Clutter 转发对象排入按下/释放，绑定在实际帧之后恢复；不触碰 Main 输入法焦点。未生效的 XTEST/XSendEvent 实验已移除，普通重放继续用已验证虚拟设备。立即来源绑定提交前节点/上下文，核对实际插入和提交后的范围/光标，等待组合结束，500ms 自动过期；IBus 面板销毁时清除旧引用。`atspi-xwayland.json`/`atspi-source.json` 和生命周期证据已更新；原生 GTK 生命周期回归通过。焦点竞态专项与最终帮助审计仍待完成，阶段 D 不标记完成。

D 最终验收（2026-10-15）：以下结果替代历史条目中的“待完成/进行中”，原需求范围未缩减。

| 项目 | 完成依据 |
| --- | --- |
| D01 | `core/text.rs` 与正式 TestTextRule 接口共享页内/全局匹配；现有规则编辑后保存及实际大小写/立即匹配、页内多行/撤销通过。Rust 测试证明四种触发、前边界、专属跨触发覆盖、停用回退、大小写、多行和输入策略；GTK/XWayland/VTE 另验证空格结尾的合法立即关键词。 |
| D02 | 原生 GTK、Firefox、Electron、XWayland GTK 的实际替换和中文多行通过；各正式路径的 Rime 组合保护、确认/立即提交通过，非终端密码跳过。真实同窗字段切换取消等待中的旧请求，新字段仍能替换；旧窗口请求拒绝。XWayland 以原键码/修饰状态和自身来源重放，Caps Lock、Shift 及按键保持均通过。 |
| D03 | 当前 Ptyxis/VTE 的 24 项检查通过 canonical、Readline、getpass、确认/立即/吞掉、中文关键词、紧邻撤销、导航/焦点/快捷键/真实粘贴清理、开关/排除/生成输入与 raw 字节。没有 Shell 插件依赖，普通和密码终端输入均参与；raw/TUI 结果仍明确为已提交而非已校验文档。 |
| D04 | 原生与 XWayland 生成内容不递归，自身按键及异步 IBus 提交抑制通过；撤销只用于当前可确认范围，导航后 core 和界面缓存均失效。开关/排除、真实状态/最近结果、锁屏、core/IBus 断连恢复、AT-SPI 注册服务重启恢复通过；鼠标未授权不阻止文本。用户帮助已加入并经实际窗口截图核对。 |

最终证据及重跑命令见 [`fixtures/phase-d/README.md`](../fixtures/phase-d/README.md)，包含实际受测扩展副本哈希、结果和帮助截图。Rust 6 + 4 项、原生组件构建/MIME/停用检查、前端类型检查/Vite、桌面 custom-protocol 构建与 diff 检查通过。主桌面未部署或重复测试。

### E：配置迁移、备份与全页面闭环（已完成，2026-10-15）

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| E01 | A03、C01、D01 | core/config：真文件导出/检查/合并/替换、冲突ID与引用重映射、未知动作/版本/递归检查、preview摘要 | 摘要对应实际文件；合并保留偏好/已有同词同应用文本；冲突模板/动作复制、冲突规则副本停用；失败不部分覆盖 |
| E02 | E01 | XDG状态中的备份、自动/手动、恢复前备份、保留最近5份、备份真导出/删除；文件对话框和确认接入 | 导入/恢复前必有可读备份；备份失败阻止覆盖；重启列表一致，恢复内容实际生效；状态/授权/记录不迁移 |
| E03 | B04、C05、D04、E02 | 逐页与逐弹窗审计，清除固定反馈/样本初始化；真实空态/错误；诊断导出与引用来源/失效提示 | UI矩阵每行均通过；原型同位置布局及操作流程一致；所有控件存在真实行为，不剩模拟运行 |

运行记录保留有界数量的状态和原因，不收集输入正文；初版最多最近100条执行摘要，设置界面不为此新增控件。诊断导出包含版本、组件、能力和错误；不包含按键流、密码、替换正文或剪贴板内容。涉及用户命令的失败提示显示原因/步骤，不在持久日志自动记录敏感参数。

### F：安装、会话生命周期与发布验收

| ID | 依赖 | 实施与代码归属 | 通过条件 |
| --- | --- | --- | --- |
| F01 | B01、A04 | Fedora44 RPM/开发安装、扩展 metadata 与连接检查、root服务/控制授权、用户会话core、desktop入口；初次向导/登录启动开关 | 安装不自动接管；管理员授权只用于鼠标服务；拒绝可重试；登录偏好真实生效；设置可在无接入时打开 |
| F02 | F01、E03 | 实机集成：多屏/缩放、弹窗/桌面/未聚焦起点、设备重插、扩展重启、锁屏/解锁、core/inputd失联、UI重开与退出 | 操作目标不偏移、不重放锁前输入、不留按键；普通操作完整恢复；设备选择身份正确；文本与手势状态独立 |
| F03 | F02 | 安装/升级/卸载、配置保留、probe与正式服务切换、release构建、最终UI比对与功能审计 | RPM可安装启动与卸载；旧探针不与inputd同时抓同鼠标；卸载停组件/移系统文件且保留用户配置；发布门槛全通过 |

开发验证继续优先独立 GNOME。真实鼠标、主桌面多屏/锁屏、安装授权和原生窗口手感只在确实需要时交给用户操作。探针保留为证据源码，正式软件不依赖 probe 安装路径、控制器或临时测试总线。

## 最终发布门槛

全部满足才能称完成；任何一项不通过都保留待办，不改名“优化项”绕过。

1. 产品规格每项对应正式实现；八个主页面、编排、初次设置、全部弹窗/状态均视觉与功能双验收通过。
2. 69项动作覆盖下方完整清单及各自操作枚举。每项注册定义、参数UI、语义校验、执行器、能力/错误和结果一致；硬件缺失与未实现严格区分。
3. 手势录制/保存/识别/起点匹配/辅助键/取消/动作真正闭环；自由轨迹保持方向/顺序/比例；无八方向量化。
4. 声明式顺序/等待/分支/有限重复/遍历/变量/调用/返回/取消全部可运行；草稿不会改变活动配置。
5. 文本各触发模式、范围、IME、确认语义、密码政策、自身抑制与撤销在代表性真实应用通过；已知raw终端限制明确，不假称全兼容。
6. 配置导入导出/合并/替换/备份/恢复真正读写文件；失败原配置完整，重启可恢复。
7. 标题栏控制真实可用；关闭设置后台继续、退出释放、锁屏取消、设备/连接失效正确恢复。
8. 正式启动路径不包含 localStorage 配置、固定成功/结果、测试服务、评审选择器、隐藏空执行器或未连接按钮。
9. 当前Fedora44/GNOME50.5原生Wayland release构建、RPM安装卸载及最终WebKitGTK视觉核对通过；不拿Chromium截图代替桌面实现验收。

## 必要验证与开发入口

阶段 A 已提供以下实际开发入口（普通用户运行，无需 sudo）：

```sh
npm ci --prefix apps/desktop
./scripts/build.sh
./target/debug/waystroke
npm run dev --prefix apps/desktop
cargo test -p waystroke-model -p waystroke-core
npm run test:adapter --prefix apps/desktop
python3 scripts/check-core.py
python3 scripts/check-ui.py
```

`build.sh` 依次生成 Rust→TypeScript 模型/协议、检查前端、构建 Vite 并构建带本地资源的桌面程序与后台。`npm run dev` 自动构建同目录后台。release 入口为 `npm run build --prefix apps/desktop`；release/RPM 验收属于 F03，阶段 A 使用已实测的 debug 原生构建。

`check-core.py` 使用私有 D-Bus 与临时 XDG；`check-ui.py` 使用独立 GNOME 50.5、原生 WebKitGTK、WebKitWebDriver 与 tauri-driver，输出真实窗口/配置检查结果和截图。所需辅助工具及路径配置见仓库 README。视觉基线保存在 `fixtures/ui-baseline/`。后续阶段继续扩展这些入口；inputd 测试、正式 GNOME 接入检查和 `packaging/build-rpm.sh` 随 B/F 落地，当前不提供空脚本冒充完成。

检查覆盖配置原子性、引用/类型/递归、真实 UI CRUD、关闭/重开/断连/退出与原生窗口。识别、编排执行、输入释放和 69 项执行器的实测按 B–F 增加；不以阶段 A 的参数往返检查替代执行器验收。

本机开发依赖已经由用户安装并核对：Rust/Cargo 1.98.1、Node22.23.1/npm10.9.8；pkg-config报告WebKitGTK4.1 2.54.1、GTK3 3.24.52、librsvg2 2.62.4。不重复要求安装。Tauri2使用实际稳定发行版本并生成Cargo/npm锁文件；不启用tray-icon/linux-libxdo。只有实际构建缺库时才按错误补充依赖。

技术栈参考：[Tauri Linux/Fedora 前置依赖](https://v2.tauri.app/start/prerequisites/)、[窗口定制](https://v2.tauri.app/learn/window-customization/)。当前进程划分和任务合同是本项目决策；既有实机依据见技术验证文档，未完成的系统动作验证归入C04/C05。

## 69 项动作实施与验收索引

以下逐行记录当前实现和隔离验收结果。证据文件位于 `fixtures/phase-c/`，斜线后为结果键。ID 沿用设计稿，参数与操作枚举以动作目录和原型字段为准；环境能力限制和未经执行的主机会话操作单独注明。隔离结果不代替主会话升级闭环。

### 键鼠输入

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `shortcut` | 发送快捷键 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-input-clipboard.json / phaseCKeyAndUnicode` |
| `key` | 按下或释放按键 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-input-clipboard.json / phaseCKeyAndUnicode` |
| `mouse` | 鼠标点击或按下释放 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-enums.json / additionalInputEnums、phaseCInput` |
| `pointer` | 移动鼠标指针 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-enums.json / additionalInputEnums、phaseCInput` |
| `scroll` | 滚动 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-scroll-target.json / scrollTargetsWindowAcrossPointerLocation、phaseCInput` |
| `drag` | 拖动 | C04 | 测试窗口收到正确键/按钮/坐标/滚动/拖动；目标校验及取消释放 | 隔离执行通过；`desktop-enums.json / additionalInputEnums、phaseCInput` |

### 文本与剪贴板

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `text` | 输入文本 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCKeyAndUnicode` |
| `paste` | 粘贴文本 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCClipboardRestoreAllMime` |
| `clipboard.read` | 读取剪贴板 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCClipboardRestoreAllMime` |
| `clipboard.write` | 写入剪贴板 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCClipboardRestoreAllMime` |
| `clipboard.clear` | 清空剪贴板 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCClipboardRestoreAllMime` |
| `selection.copy` | 获取选中文本 | C04 | 实际文字/剪贴板变化与输出一致；临时恢复和旧内容排除 | 隔离执行通过；`desktop-input-clipboard.json / phaseCSelectionCopy` |

### 应用与命令

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `launch` | 打开程序 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`desktop-apps-session.json / applicationArgumentsAndNewTarget` |
| `app.activate` | 激活或打开应用 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`desktop-apps-session.json / applicationActivateExisting` |
| `command` | 运行命令 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`execution-final-data.json / directAndShellCommands` |
| `uri.open` | 打开链接或文件 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`execution-final-data.json / actualUriHandler` |
| `app.quit` | 关闭应用窗口 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`desktop-apps-session.json / applicationQuitOne` |
| `process.signal` | 向进程发送信号 | C03/C04 | 实际程序/窗口/进程状态及退出结果；目标和超时正确 | 隔离执行通过；`execution-final-data.json / asyncAndSignal` |

### 窗口与工作区

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `window` | 窗口操作 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `window.find` | 查找窗口 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `window.target` | 设置动作目标窗口 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `window.info` | 读取窗口信息 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / windowInformationAndTargetEnums` |
| `window.geometry` | 移动或调整窗口尺寸 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `window.monitor` | 移动窗口到显示器 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `workspace.switch` | 切换工作区 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `workspace.move` | 移动窗口到工作区 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `desktop.overview` | 概览或应用列表 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |
| `desktop.show` | 显示桌面或恢复窗口 | C04 | 真实窗口/工作区/显示器状态变化或信息输出；目标失效报错 | 隔离执行通过；`desktop-enums.json / phaseCWindows` |

### 流程控制

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `wait` | 等待时长 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |
| `wait.condition` | 等待条件成立 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`desktop-integration.json / representativeWaitFindTargetInput` |
| `condition` | 条件分支 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |
| `repeat` | 有限次数重复 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |
| `foreach` | 遍历列表 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / typedForeach` |
| `loop.break` | 退出当前重复 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / nearestLoopControl` |
| `loop.continue` | 跳过当前循环项 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / nearestLoopControl` |
| `flow.stop` | 停止动作序列 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / stopWholeNestedSequence` |
| `flow.call` | 调用可复用动作 | C02 | 真实步骤顺序/分支/循环/等待/调用结果及取消/超时 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |

### 变量与数据

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `variable` | 设置变量 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |
| `variable.read` | 读取上下文值 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / contextDateRandom` |
| `number.calculate` | 数字计算 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / scopedNestedCallAndRepeat` |
| `text.transform` | 处理文本 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / jsonListUnicodeChain` |
| `date.format` | 格式化日期时间 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / contextDateRandom` |
| `number.random` | 生成随机数 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / contextDateRandom` |
| `json.parse` | 解析 JSON | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / jsonListUnicodeChain` |
| `data.field` | 读取数据字段 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / jsonListUnicodeChain` |
| `list.change` | 操作列表 | C03 | 真实类型化输出被后续步骤消费；作用域与参数类型正确 | 隔离执行通过；`execution-final-data.json / allListOperations` |

### 文件与路径

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `file.read` | 读取文本文件 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / realFiles` |
| `file.write` | 写入或追加文本文件 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / realFiles` |
| `file.copy` | 复制文件或目录 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / directoryCopyMoveAndSymlink` |
| `file.move` | 移动或重命名 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / directoryCopyMoveAndSymlink` |
| `file.trash` | 移到回收站 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / actualTrash` |
| `directory.create` | 创建目录 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / realFiles` |
| `directory.list` | 列出目录内容 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / directoryOverwriteAndRecursiveFilter` |
| `file.info` | 读取路径信息 | C03 | 临时目录中的实际文件/目录状态及输出；冲突策略正确 | 隔离执行通过；`execution-final-data.json / allFileInfoProperties` |

### 系统与媒体

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `volume` | 调节音量或静音 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-audio.json / phaseCRealPrivateAudio` |
| `brightness` | 调节亮度 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 当前无背光，明确不可用且执行失败；硬件分支保留；`desktop-system.json / phaseCBrightnessUnavailable` |
| `media` | 控制媒体播放 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`execution-final-data.json / mprisAllOperations` |
| `notification` | 显示通知 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-system.json / phaseCNotification` |
| `dialog.message` | 显示消息或询问 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-system.json / phaseCNativePromptWithoutUI` |
| `dialog.input` | 请求用户输入 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-system.json / phaseCNativeInput` |
| `screenshot` | 截图 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-system.json / phaseCFullScreenshot` |
| `session` | 锁屏或会话操作 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离实际锁屏通过；注销/挂起私有服务契约及权限失败通过，未自动操作主会话；`desktop-apps-session.json / sessionActualPrivateLock` |
| `settings.open` | 打开系统设置 | C05 | 对应系统/媒体真实效果或已核实能力限制；取消/权限原因准确 | 隔离执行通过；`desktop-apps-session.json / actualSystemSettings` |

### 高级集成

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `http.request` | 发送 HTTP 请求 | C03 | 本机fixture HTTP/D-Bus收发及类型化结果；错误/超时正确 | 隔离执行通过；`execution-final-data.json / realHttpAndTypedField` |
| `dbus.call` | 调用 D-Bus 方法 | C03 | 本机fixture HTTP/D-Bus收发及类型化结果；错误/超时正确 | 隔离执行通过；`execution-final-data.json / dbusTypedArgumentsAndReturns` |
| `dbus.property` | 读取或设置 D-Bus 属性 | C03 | 本机fixture HTTP/D-Bus收发及类型化结果；错误/超时正确 | 隔离执行通过；`execution-final-data.json / dbusPropertiesAndEmptyCall` |

### WayStroke 控制

| 动作 ID | 动作 | 任务 | 通过证据 | 状态 |
| --- | --- | --- | --- | --- |
| `waystroke.toggle` | 控制手势或文本替换 | C03 | 真实启停/规则/页面变化，配置或会话状态符合语义 | 隔离执行通过；`execution-final-data.json / realWayStrokeControl` |
| `waystroke.rule` | 启停指定规则 | C03 | 真实启停/规则/页面变化，配置或会话状态符合语义 | 隔离执行通过；`execution-final-data.json / realWayStrokeControl` |
| `waystroke.open` | 打开 WayStroke 页面 | C03 | 真实启停/规则/页面变化，配置或会话状态符合语义 | 隔离原生执行通过；`native-editor-final.json / realWayStrokeOpenAction` |

优先细查的特殊语义：显示桌面恢复仅恢复本程序保存的窗口状态；截图覆盖选区/窗口/全屏与文件/剪贴板输出；音量包含默认输入/输出；亮度受实际设备能力限制；MPRIS按播放器能力报告；命令不等待与等待有不同结果结构；文件覆盖/重命名/回收站使用真实策略；所有窗口操作枚举不能只实现最大化；HTTP全部方法及D-Bus读取/设置/调用均需接入。交互询问、请求输入在设置未打开时仍可完成或明确取消。

## 当前实施进度

A–E 已完成，具体证据见本计划及 `fixtures/phase-b`、`fixtures/phase-c`、`fixtures/phase-d`、`fixtures/phase-e`。下一阶段为 F 的系统级安装、会话集成与发布验收；E 提前接入的向导操作不代表 RPM 或主系统授权已验收。原设计稿保持不变。

## XWayland 兼容替换（2026-10-22）

依据技术验证第五阶段实现选区校验替换，默认对所有没有 AT-SPI 文本接口的 XWayland 应用启用，可按应用停用：

- core `xselection.rs`：x11rb 连接 XWayland（扩展在 X11 窗口获得焦点时传入 Shell 的 DISPLAY 与认证文件，失焦即断开）；XI2 raw 按键维护输入尾部并按送达顺序识别用户插入的按键；XFixes 选区通知与 PRIMARY 读写；探测、逐字校验、词边界与字段开头判断、粘贴、修正与撤销。`atspi.rs` 区分可编辑、密码/不可用与没有文本接口三种焦点，只有最后一种回退。
- 扩展：`textKeys` 只向 core 校验过的窗口发送按键；立即规则的末字符在没有 AT-SPI 输入来源时交给兼容替换；状态说明区分兼容替换、已停用与 X11 终端。
- 配置：`Exclusion.compatibility`（旧配置默认 false）；运行结果增加应用标识，运行状态页对“不导出选区”的应用提供停用按钮，设置页排除行增加“停用兼容替换”。
- 验证：`check-gnome.py --devkit --release --phase-d-atspi --selection` 与 `check-ui.py --devkit --release --selection-ui` 通过，证据见 `fixtures/xwayland-selection/`；`--phase-d-atspi --ime --lifecycle`、`--phase-d-text` 回归通过。默认 `check-ui.py --devkit --release` 在手势画布录制步骤超时，同一命令在改动前的 HEAD 上同样失败（私有会话取不到鼠标服务），与本项无关。

## 阶段 A 实施记录（2026-10-13，已完成）

| 任务 | 正式实现 | 验收证据 |
| --- | --- | --- |
| A01 | Cargo/Tauri 2/Vite/TypeScript 工程及锁文件；`scripts/build.sh`；原型客户区 DOM/CSS；原生窗口控制 | 最终统一构建通过；独立 GNOME Shell 报告 clientType=0；八页、编排与九类弹窗截图归档；缩放、最大化/还原、拖动、最小化/恢复、连续滚动/固定保存栏均通过 |
| A02 | `crates/model` 配置/步骤 AST/类型化绑定/起点与执行结果模型；69 项参数目录；Rust→TypeScript；语义校验 | model 测试定位未知动作、不可见引用、类型错误及间接递归；adapter 检查覆盖全部 69 项参数、主样本/轨迹、结构化 D-Bus/布尔值、接口默认与返回值、稳定引用改名；原生动作复制后局部输出和返回字段引用正确重映射 |
| A03 | `crates/core` 唯一写者、revision/保存时间、XDG 路径和原子保存；前端配置、草稿、计数与筛选来自真实快照 | 原生 UI 实际创建规则/模板/动作/文本；设置保存、复制删除与重开恢复通过；私有 D-Bus 检查四类文档后台重启恢复；冲突、校验及实际 I/O 失败不改变旧文件/活动版本；断线失败保存保留草稿，取消恢复活动配置 |
| A04 | 会话 D-Bus/UID 核对/配置事件；Tauri 受限桥接、协议版本检查、单窗口、独立后台、重连快照与真实退出 | 重复 core 立即失败；重复 UI 恢复已有窗口；关闭设置后 core 存活；重开读取真实配置；断线可编辑但禁止假保存；重连重新读取快照；运行状态页退出使 core 与窗口均停止 |

最终验证命令：`./scripts/build.sh`、`cargo test -p waystroke-model -p waystroke-core`、`npm run test:adapter --prefix apps/desktop`、`python3 scripts/check-core.py`、`python3 scripts/check-ui.py`。Rust 4 个必要测试、前端 6 组数据往返检查及真实 D-Bus/原生窗口检查通过。`fixtures/ui-baseline/native/results.json` 保留最终逐项结果；截图和原型哈希见同目录 README。初次配置为空，不安装示例自动化；正式代码不依赖 localStorage 或 probes 运行服务。

视觉核对保持侧栏/标题栏/主区尺寸和间距。GTK 选择框多出的 8 像素已校正为 Chromium 的 43 像素，设置行恢复为 80 像素；轨迹/颜色滑块及品牌图标已对照。字体抗锯齿存在引擎差异；设备、选窗和执行详情内容显示当前实际未接入能力，不保留模拟成功。

本机 NVIDIA 的 WebKitGTK Wayland Error71 经独立实测由 `__NV_DISABLE_EXPLICIT_SYNC=1` 解决；正式启动仅在检测到 NVIDIA 模块且用户没有指定该变量时应用，不关闭 DMABUF/硬件合成。依据：[Tauri 图形问题说明](https://v2.tauri.app/develop/debug/linux-graphics/)。GNOME Wayland 最小化后重复启动通过重新映射同一个原生窗口恢复，保留 WebView 和草稿；仅调用 GTK deiconify 的原生测试曾失败，修复后通过。原生验证依据：[Tauri WebDriver](https://v2.tauri.app/develop/tests/webdriver/)。

阶段 A 是可运行的配置编辑工程。桌面扩展、输入接管、69 项执行器、全局文本替换、配置迁移/备份和发行包按 B–F 继续实现，当前界面明确报告这些能力不可用。

## 阶段 B 实施记录（2026-10-13；下文为过程记录，最终结论见末尾）

- B01：已建立 Rust inputd 工程、相对鼠标/触摸板筛选、udev 稳定身份、同 UID Unix socket、异步推送、3 秒租期及 250 毫秒起点/结束确认看门狗。设备准备与实际接管分离；状态机由 core 的逻辑坐标结果决定点击重放或手势消耗，不使用原始计数替代 12 像素。输入服务编译与鼠标状态机必要测试通过，开发安装脚本和 systemd 单元已安装，真实 G304 发现和仅准备/释放通过，尚未接管真实鼠标。G304 还声明键盘宏能力：不再按 F24 能力误排除鼠标，原设备宏键转发与内部同步标记使用不同合成设备。主机 udev 已确认设备分类就绪；沙箱内 `/dev` 快照不可用，实际设备检查在主机完成。
- B02：正在落实 uinput→Mutter 的显式输入屏障。仅冻结后续运动不能证明此前运动已消费；已由限定虚拟设备的 F24 标记触发 Shell 快照，再确认输入状态机。合成器设备加入事件确认两个设备就绪后才发送首个标记，不使用固定等待时间。标记不采集物理键盘；实际可用性、修饰键影响、设备初始化顺序与负载时序仍须独立 GNOME 证明，失败不能按固定等待时间放行。
- B02 接口增量：正式 GNOME 扩展已在独立桌面加载；50.5/版本握手、窗口身份、快捷键定位 A 而非焦点 B、窗口最大化、关闭后不重定向检查通过（`scripts/check-gnome.py`）。输入屏障尚未取得真实 uinput 端到端证据，不能据此认定 B02 完成。
- B03：Rust 64 点弧长重采样/等比缩放/平移、指数距离分值、多样本、阈值/同级歧义、应用/标题优先级、辅助集合与排除已实现。尺度平移、反向/旋转/比例、停用专属回退、歧义与最小长度检查通过；模板/规则试画对比及测试页已调用同一 Rust 算法，原生测试页的已保存自由轨迹实测为 100.0%；真人样本效果仍待验证。后续修正：逐点按序号比较时，多段形状（如 e）的各部分长度占比一变，后续所有点都会错位，同一手势的真人样本互评仅 25–83 分；改为带宽 8 的 DTW 对齐，分值改为 exp(−2·平均距离)，使默认阈值 82 对应约 0.1 倍轨迹尺寸。用户现有 7 个手势的样本留一互评全部 ≥84.5，不同手势之间最高 69.7。
- B04：扩展轨迹/逻辑坐标采样/取消及基本桌面接口代码已落地；正式 core 调度、真实运行状态/选设备/选窗/识别页面已联通；原生 UI 的画布→保存→正式识别→选真实窗口→入队→执行详情检查通过。物理输入屏障、轨迹反馈/取消、性能测量与用户实机闭环仍待完成。阶段 B 不算完成。

当前验证入口与范围：`scripts/check-input.py` 对已安装服务检查 G304 准备、显式释放、控制断开和租期到期释放；不发送同步按键、不接管物理输入。实测租期释放 3074.1 ms。`scripts/check-gnome.py` 检查正式扩展及 core 的实际快捷键、最大化、应用启动/窗口结果、当前与排队任务取消；排队取消没有开始时间。`scripts/check-core.py` 检查录制互斥与 UI 会话断开清理。`scripts/check-ui.py` 已同时加载正式扩展与原生窗口，检查真实识别、选窗、运行记录/详情和页面生命周期。

录制区域由同一 UI D-Bus 身份建立互斥状态，离开区域/页面或 UI 身份断开后清除；期间不执行已保存规则。状态刷新保留已有提示节点，避免录制期间画布位移。运行记录使用真实规则名称与步骤动作名称；诊断摘要分别显示起点确认、松键→识别/入队/执行以及排队时间，无实机记录时明确显示尚无实测。

主会话接入脚本为 `scripts/install-dev-extension.sh`（普通用户运行，保留其他扩展设置；新版本需要注销/重新登录 GNOME）。已向用户提供命令，等待会话加载后再做真实 uinput 屏障与 G304 手势检查。B 阶段仍在进行，不以隔离接口/页面结果代替物理输入验收。

扩展总线名称定为 `io.github.waystroke.Gnome`（路径 `/io/github/waystroke/Gnome`，接口 `io.github.waystroke.Gnome1`）；原计划中的 Desktop 名称与 Tauri 的 GTK 应用标识冲突，正式扩展与原生 UI 联测已发现并修正。应用标识保留 `io.github.waystroke.Desktop`。

用户要求安全暂停（2026-10-13）：隔离检查进程已退出，主机确认不存在 `WayStroke Virtual` 输入设备，正式服务空闲。最新统一构建、core 检查及必要 Rust 测试通过；上一轮正式扩展/原生 UI 联测通过，但最后一次 `check-ui.py` 重验出现 WebDriver HTTP 500，日志 `/tmp/waystroke-ui-phase-b.log`、结果目录 `/tmp/waystroke-ui-check-f7mi04og`，恢复时先定位此失败，不能把最后重验计为通过。下一步等待用户安装当前扩展并注销/重新登录，再验证主会话屏障与真实 G304；阶段 B 未完成。

恢复后增量：已确认主会话正式扩展 ACTIVE、50.5 握手成功，安装文件与仓库 SHA-256 一致。仅准备合成设备、等待 GNOME 实际设备就绪并发送 Ready 标记，正式扩展成功返回对应序号快照；本次未 Activate、未接管 G304。首个 Ready 标记至 Shell 快照实测约 73.0 ms，此值不是手势松键延迟。物理手势 Begin/Finish、跨窗、取消及动作闭环仍待实测。最后 UI 重验失败发生在复制配置已落盘、对应删除按钮尚未渲染时；检查脚本现等待目标 DOM 后再点击，并保留 WebDriver 错误正文。

实机第一轮反馈：G304 正式接管成功；用户报告绘制时明显卡顿并影响桌面。已暂停 gesturesEnabled 并释放鼠标。三次轨迹中一次执行成功（Probe A 回车计数 1，B 为 0），普通右键点击已记录。松键→识别实测 2.3–4.7 ms，成功次松键→开始约 2.7 ms；不能以这个延迟替代绘制流畅性验收。选窗保存遗漏显示名称已修复，主 UI 已重开；回归脚本已证明选窗保存成功，但后续第二次试画等待录制状态未通过，尚待定位。当前优先修复绘制期间全屏 Cairo 重绘及无消费者的逐点通知开销，之后再做实机复测。

绘制性能修复：轨迹从全屏 St.DrawingArea 改为无纹理容器下的 256×256 局部分块，仅刷新当前线段经过的分块；保留屏幕逻辑坐标、3 px 线宽、颜色和完整识别样本。删除无人消费的 Shell 逐点 D-Bus 通知。`scripts/check-trail.py` 只在临时扩展副本加入基准入口，在同样 2560×1440、软件渲染、3 秒轨迹下比较：原版 Shell CPU 1.34 s，分块版 0.22 s，均 180 帧。证据见 fixtures/phase-b/trail-before.json 与 trail-after.json；这些数值不是实机流畅性验收。主会话仍运行旧扩展，手势保持暂停，更新并重新登录后才复测。

当前 UI 全流程回归已再次通过：选取真实窗口后保存应用显示名称、正式识别、录制切换释放、真实执行详情、草稿/重开/断连/退出。销毁画布时已移除残留指针事件并使销毁幂等，避免旧画布离开事件清除新画布的录制状态；退出确认前先释放输入并取消任务。输入服务连接尝试移至可取消后台任务，防止占用/慢握手阻塞录制身份断开等控制事件。分块轨迹实际合成画面已检查连续性，见 fixtures/phase-b/trail-tiles.png。当前扩展文件已更新，GNOME 仍需用户重新登录加载；全局手势保持暂停。

多屏增量验证：`scripts/check-gnome.py --multi-monitor` 在隔离 GNOME 使用 1440×1000 与 1280×900 两个显示器，确认起点 A 在 monitor 0、移动到 monitor 1 的 B 后返回逻辑坐标 [1800,300]，先前冻结的 A 身份保持不变。基本快捷键/窗口/启动及队列取消检查同时通过；证据 fixtures/phase-b/desktop-multimonitor.json。此结果只证明多屏接口与坐标，不替代实机输入屏障及负载时序。主会话只读确认仍为旧扩展实例，仍等待用户重新登录后复测性能。

性能实机复测：用户重新登录加载当前分块扩展，文件 SHA-256 一致，新实例 a181d9cd-1414-4ddb-bd65-3094b5642098。用户反馈“这次很流畅”。三次人体轨迹中两次匹配并向 Probe A 实际发送回车（分值 85.97%、92.47%），另一次 62.69% 未达到 82% 阈值，未执行；普通右键被判为 tooShort。成功次松键→开始约 2.75 / 3.42 ms。被动事件/轨迹/CPU 证据见 fixtures/phase-b/live-performance-retest.json；仍须实测跨窗、取消、辅助键及启动/窗口动作。已准备复用原模板的 Probe 专属左键辅助最大化、中键辅助计算器规则。

实时规则名称增量（用户明确要求）：正式 GNOME 轨迹下方增加非交互标签，随自由轨迹与手势期间任意时机按下的辅助键更新。Shell 每 50 ms 最多发送一次增量坐标；core 使用冻结的起点上下文/配置与正式 Rust 算法预览，不入队执行，仅在文本变化或辅助键交互时回传。未匹配/歧义/短轨迹分别显示“未匹配”“手势相近”“绘制手势…”。标签位置由 Shell 本地更新，不跟随采样频率发送 D-Bus；下方越屏时移到上方。结束、取消、释放及锁屏清除。辅助键点击可发生在绘制后、右键松开前，已按过的辅助键保留至结束，实际辅助键交互更新停留计时。

必要 Rust 检查通过，新增测试证明先移动、再点击并松开左键、最后松右键仍通知并保留辅助键。隔离 GNOME 的标签更新/清理与真实合成画面通过；2560×1440 软件渲染 3 秒、181 帧、54 次增量预览，Shell CPU 0.28 s（先前无标签分块版 0.22 s，全屏旧版 1.34 s）。证据 fixtures/phase-b/trail-live-name.json 与 trail-live-name.png。此检查验证显示及批处理，不替代实体鼠标到 core 预览的实机联测；新版扩展需重新登录加载。

实时名称新版已安装到用户扩展目录，core 已重新编译，core D-Bus 回归通过。为重新登录已保存 gesturesEnabled=false；主机会话确认 inputArmed=false、WayStroke 虚拟设备 0、运行/排队任务 0。现等待用户保存草稿并注销/重新登录，随后重开新版程序，继续实体鼠标预览、晚按辅助键及阶段 B 剩余验收。配置与模板保留，不需要重新安装 root 输入服务。

用户明确要求安全暂停以注销（实时规则名称更新后）：再次主机核对 inputArmed=false、虚拟输入设备 0、运行/排队动作 0。新版扩展已安装，core 已构建；恢复时先确认 GNOME 新实例及安装文件一致，再重开程序验证实时预览与晚按辅助键。暂停期间不继续开发或输入测试。

恢复实时名称验证：主会话新实例 58fd5733-ce1b-4857-9b16-815e3beea278、GNOME 50.5、未锁屏，安装扩展与仓库一致。新版 core/UI 已打开，测试前保持手势暂停；用户当前 revision 19 配置中已停用实机回车，实机最大化辅助键为空，计算器使用中键，保留这些用户修改。已打开自有 Probe A/B 与被动记录，等待用户验证名称及中途辅助键。上一轮完整证据补齐为 21 次事件/20 条有效轨迹/5 次成功实际动作（回车 2、最大化 2、计算器 1）；用户反馈流畅但难触发，因此识别质量仍待改进和评估，不算 B03 完成。

用户确认新版实机实时名称、中途辅助键、动作与流畅性“没什么问题”。记录 fixtures/phase-b/live-name.json；用户另外要求执行提示屏幕下方居中及逐规则开关，不要求再验收此修改。已实现规则 feedback 字段（旧配置默认 true）、编辑器/HTML 同步、adapter 双向保存、全局与规则开关共同控制实际执行反馈。提示使用起点显示器的实际宽高与标签尺寸水平居中，距底 64 px。统一构建及必要 Rust 检查通过，原生 UI 自动回归证明开关保存；独立双屏真实执行证明提示位置。Esc 与 1200 ms 停留取消在独立 GNOME 清除实时标签，关闭轨迹仍显示标签。证据 fixtures/phase-b/desktop-cancel-feedback.json 与更新后的 ui-results.json。

后续实机跨窗记录已加入输入 Finish 屏障的 endContext，不额外查询当前窗口；动作始终使用冻结起点。B01 仍须设备重插、锁屏释放实测，B02 仍须连续移动/负载时序的物理证据，B04 仍须普通点击/有效未识别/取消不出菜单的物理检查。新提示位置需 GNOME 重新登录加载（更新文件不会替换当前 Shell 内已加载模块），不要求用户再次验收提示开关。

执行提示更新已安装，当前主会话手势已暂停；确认 inputArmed=false、虚拟输入设备 0、运行/排队动作 0。等待用户重新登录加载新版，再自动重开新版程序准备阶段 B 剩余实机测试。

用户明确更正扩展更新流程：后续直接重新开启 WayStroke 扩展，不默认注销/重新登录；重新开启后检查新实现实际生效。此前文档中将注销表述为唯一方法的说明不再作为操作要求。

最新实机跨窗/取消验收：用户确认整组步骤均符合预期。物理序号 2 起点 Probe A、Finish 屏障终点 Probe B、识别 90.9%、实际最大化 A；空白区普通右键记录完整 press/release 1 对；圆圈 26.6% 未执行；Esc 与停留取消均记录且无 gestureError。证据 fixtures/phase-b/live-crosswindow-cancel.json。

用户要求取消按右键后的“绘制手势…”提示，已修改为最小长度前标签隐藏并构建 core。用户指定直接重新开启扩展，已实际执行 disable/enable，新实例 1130fc5c-ae35-4aa1-a813-cae5fdf9b455，但 hello 未出现新源码中的 capabilities，证明只重新创建旧 ESM 模块实例。当前 GNOME 50.5 官方 ReloadExtension 接口返回 UnknownMethod: Method ReloadExtension is not implemented。主会话新提示修改未加载，不得以新实例或磁盘 SHA 一致宣称新代码运行。已恢复后台以继续剩余锁屏/重插验收；新版加载仍待解决，不使用 unsafe Eval。

取消初始提示的新源码在独立 GNOME 已验证：initialLabelHidden=true，匹配后名称显示，结束后 labelCleared=true；3 秒软件渲染 Shell CPU 0.22 s，证据 fixtures/phase-b/trail-quiet-start.json。当前主会话仍复用旧模块，不能据此宣称该显示变化已在主会话加载。最新 core 已启动、规则逐项开关已加载，UI 保留，等待锁屏/重插实机步骤。

用户明确决定跳过重插验证。真实 G304 物理重插、软件重建设备及强制 event 编号变化不再作为本轮需用户执行的步骤，标记为“用户选择跳过，未验证”，不能宣称硬件重插验收通过。未执行任何解绑操作，临时准备的重建脚本已移除。锁屏实机行为用户确认正常；记录显示扩展离线时 inputArmed=false、解锁后 true 并实际执行成功。发现锁屏扩展被停用造成状态误报，core 已改为订阅 GNOME 原生 ScreenSaver.ActiveChanged，并初始化 GetActive；独立 GNOME 原生遮罩已证明 locked=true/桌面已锁定、取消运行和排队动作、队列未开始、恢复可用。

原生锁屏状态修复已在主会话 core 重启加载，inputArmed=true/locked=false/正常接入核对通过。对旧格式规则新增 feedback 默认值的 core 回归已修正为比较规范化后的真实配置，并证明旧配置默认 true、重启保持。剩余收尾：最后扩展模块实际加载（能力声明仍缺失，已向用户说明本机缓存限制）与受控负载/连续移动物理起点确认；重插按用户指示跳过。为会话重启已保存 gesturesEnabled=false，窗口与规则保留。

## 阶段 B 收尾结论

阶段 B 实施完成。用户明确跳过重插验证，该项保留为未验证，不计作通过；其余阶段 B 要求已按下表核对。C–F 不属于本次完成范围，69 项动作与文本替换等仍按后续计划实施。

| 项目 | 实现与最终证据 | 结论 |
| --- | --- | --- |
| B01 | G304 实际发现/接管/点击/辅助键；限定设备与同 UID 控制；准备/释放、控制 EOF/租期检查见 input-preparation.json；主会话退出释放检查、用户锁屏反馈及 live-lock.json；原生锁屏状态和队列取消见 desktop-native-lock.json。稳定身份与重新接入设备信息更新已实现。 | 完成；真实重插及强制 event 编号变化按用户指示跳过，未验证。 |
| B02 | live-crosswindow-cancel.json 与 live-load.json 显式记录 A 起点/B 终点，实际动作作用于 A，用户按要求先使 B 获焦点；desktop-multimonitor.json 验证双屏逻辑坐标，desktop-native-lock.json 含关闭目标不重定向；录制区域/唯一 UI 身份互斥及生命周期见 ui-results.json、check-core.py。当前桌面手势未结束时拒绝提前进入录制状态。 | 完成。 |
| B03 | Rust 正式算法与必要测试：弧长 64 点、统一缩放/平移、保留方向/顺序/比例、多样本、阈值/歧义/范围优先级与回退；live-performance-retest.json、live-name.json、live-load.json 保存真人样本评估，低分不执行。用户确认实时名称与绘制手感正常。 | 完成；不把样本匹配比例或相似度当作成功概率保证。 |
| B04 | 原生 UI 录制/保存/重开/真实算法/执行详情见 ui-results.json，实机快捷键、最大化及计算器见 live-performance-retest.json；点击透传、不同轨迹不执行、Esc/停留取消见 live-crosswindow-cancel.json；辅助键可绘制后点击；实时名称与逐规则执行提示开关已实装并同步设计。 | 完成。 |

最终部署核对：GNOME 新实例 1463d264-2012-413a-be30-85506e6d3299 的 hello 明确包含 liveRuleName/bottomFeedback/quietGestureStart，证明已加载最终模块；取消初始“绘制手势…”提示已由独立实际 Shell 检查证明隐藏，见 trail-quiet-start.json。最后原生 UI 回归包含逐规则反馈保存、正式录制/识别/执行及退出，complete=true。

负载验收：后台 30 秒单核进程退出码 0；两次成功跨窗手势起点、结束与识别均处于该负载时间范围内，起点 A/终点 B，实际最大化 A。起点绑定 3.76/3.84 ms，松键→识别 3.19/3.43 ms，松键→入队 3.55/3.75 ms；用户反馈“没问题”。该证据限定为所定义的单核负载，不宣称所有负载的时延保证。其余低分轨迹未执行。见 live-load.json，完整执行开始时间和排队时间保留于事件 timing。

安装/更新说明已按实际 GNOME 50.5 源码与运行结果修正：直接重新开启仅重新启用已导入模块；代码更新受 ESM 缓存限制，需要新桌面会话。不使用 unsafe Eval、不把实例变化或磁盘文件一致误当作新代码加载证明。


### 阶段 C 实施进展：参数与执行快照

阶段 C 已开始，C01–C05 及 69 项动作仍按原合同实施，不以现有阶段 B 执行能力代替完成。

- 新增 `core/parameters.rs`：固定值、稳定 ID 引用、嵌套对象/列表、文本模板真实求值；字段和列表索引读取保留类型，失效引用及类型不符报错。
- 执行任务同步冻结可复用动作定义，避免排队期间配置修改影响调用；调用执行尚待接入。
- 新增纯数据执行器，接入变量赋值、数字计算、文本处理和字段读取。按 Unicode 字符截取与计数；除零和无效字段真实失败。列表合并的正式校验和编辑器参数类型同步修正。
- 已通过 core 库测试（含新增嵌套求值/模板/类型检查），尚未进行完整 C 验收，当前运行中的用户程序未替换。
- 下一步：递归编排执行、局部作用域、调用参数/返回、取消/超时和实时步骤事件，再逐类完成 I/O 与 GNOME 系统动作及 UI 接入。

### 阶段 C 增量：流程、I/O 与窗口桥接

- C02 已接入正式递归执行器：分支、有限重复/遍历、break/continue/stop、可复用输入和类型化返回、局部作用域、失败后继续、嵌套超时、实时步骤事件与输出、取消当前/排队任务。调用定义与顶层步骤一同冻结。真实 core 私有总线检查证明顺序与作用域、排队期间修改调用定义仍执行原快照、超时关闭运行中的子步骤、未开始的队列取消没有开始时间。显式 flow.stop 结束整个序列；失败继续仍保留失败总体结果。
- C03 已接入变量/数据、日期时区、随机数、文件、命令、HTTP、D-Bus 与配置启停执行器。文件目录返回排序的文本路径列表；命令结果 pid/exitCode/stdout/stderr，异步 exitCode 为 null；非零退出码可被后续条件消费，命令超时/取消清理本次进程组。HTTP 返回 status/headers/body。D-Bus 参数完整覆盖设计表单的 s/i/d/b/as；方法返回 values 类型化列表、属性返回 value，权限与超时真实失败。JSON null 保留为独立值，JSON 根类型可通过结果类型选择声明。测试结果见 `fixtures/phase-c/execution-io.json`，未验证项不能据此计作通过。
- C01 同步当前遍历项类型选择到正式目录、HTML 和编辑器，支持直接遍历文本文件路径列表；循环项在运行时校验声明类型。修复列表参数与列表合并的类型校验。打开 WayStroke 页面已接原生启动参数/已有窗口导航，仍待原生 UI 验收；取消页面切换按已有草稿确认流程处理。
- C04 窗口/工作区桥接已取得独立 GNOME 双屏实证，见 `desktop-windows.json`。所有配置中的窗口操作枚举、查找排序、百分比几何、显示器和工作区操作、显式窗口变量目标及显示桌面恢复通过。半屏使用当前显示器工作区几何；编号面向用户为 1 起，底层起点快照保持 0 起供反馈使用。键鼠与文本输入仍在验证。
- 输入实测发现 Unicode keyval 在当前布局没有键码时不会产生输入，原先 void API 的返回不能证明文字成功。已加入原生文本提交或明确能力错误，完整 Unicode/临时粘贴路径继续接入。当前失败证据 `/tmp/waystroke-desktop-check-v3pd4scv`，未记为通过。
- 保留全部剪贴板格式需要多 MIME MetaSelectionSource。已实际证明 GJS 无法实现带 callback 参数的 read_async vfunc，因此增加很小的原生 C source，使用本机 50.5 开发头文件编译，GJS 调用原生 factory；不降低为只恢复纯文本。`scripts/build-clipboard-native.sh` 和 `check-clipboard-source.mjs` 已证明 UTF-8/HTML/二进制逐字节读回，见 `clipboard-source.json`。开发 SDK 下载并解压在 `/tmp/waystroke-mutter-sdk`，没有系统安装；可通过 WAYSTROKE_MUTTER_SDK 指定该 SDK。正式构建、安装、应用端粘贴确认与恢复尚待接入。当前主会话扩展未更新。

继续工作：完成剪贴板/选中文本/原生输入的端到端接入与检查，再完成系统媒体、截图和无 UI 窗口时的对话框、能力注册及 69 项核对，最后进行原生编排/UI 全流程验收。C01–C05 均未宣布整体完成。

### 阶段 C 增量：剪贴板与系统动作的实际接入

- 正式剪贴板事务已接入 core/GNOME：读取、写入、清空、复制选中文本、临时/保留粘贴及自动文本输入。临时粘贴保存所有 MIME 字节，成功和取消恢复；用户期间主动复制的新内容优先。应用未读取时真实超时，复制没有产生新 selection 时不读旧剪贴板。原为空的剪贴板也按空 selection 恢复。
- 修复 Ctrl+字母快捷键错误使用大写 keysym 而意外合成 Shift；输入实测确认 ASCII/Shift、Unicode 自动粘贴、五个按钮、四向滚动、指针与拖动、持有按键超时释放。`desktop-input-clipboard.json` complete=true，范围仅为该独立桌面检查。
- GNOME 50.5 的缓存管理器会在 owner-changed 内同步预读取新剪贴板，不能据此宣布应用粘贴。正式事务在 set_owner 返回后重置计数，只确认后续读取；不使用固定延迟猜测。依据是当前版本 [clipboard manager 源码](https://raw.githubusercontent.com/GNOME/mutter/50.5/src/core/meta-clipboard-manager.c) 和 [selection 源码](https://raw.githubusercontent.com/GNOME/mutter/50.5/src/core/meta-selection.c)，实际无粘贴读取的超时与恢复检查通过。
- C05 已接入真实 GNOME 通知、无需设置窗口的消息/询问/输入对话框、全屏/目标窗口/选区截图、文件/PNG 剪贴板输出与取消。输入框 Enter 实际确认，Esc 返回取消错误而不是有效空字符串。`desktop-system.json` 包含实际模态 UI、通知与 PNG 文件/selection 结果；没有设置窗口也通过。
- 音量与静音已在私有 PipeWire/Pulse 加仅策略 WirePlumber 下验证，完全不加载硬件监视器。虚拟输出与独立虚拟输入分别通过设置/增减音量、静音/取消/切换共 12 项，pactl 读回实际服务状态，见 `desktop-audio.json`。无可控制背光的独立 GNOME 正确报告能力缺失；没有把亮度请求当作成功。
- MPRIS 的八种操作和微秒 Seek 参数、能力不支持时不调用动作已由实际标准接口 fixture 验证，见 `execution-io-media.json`；它验证协议和 executor，不宣称用户播放器均支持所有操作。
- 系统设置、锁屏/挂起/注销执行器已经接入，但其完整验收、能力注册和 69 项逐条核对仍待完成；不在用户主会话自动执行注销或挂起。打开 WayStroke 页面的原生启动参数已按真实 sidebar 路由修正为 rules/text/test/settings，仍待 UI 实测。
- 统一构建现在包含原生剪贴板组件。`install-dev-clipboard.sh` 负责安装其独立共享库和 typelib，扩展安装脚本同步复制全部 JS 模块；脚本已检查，尚未在主机安装或更新主会话扩展。开发 SDK 仍位于 `/tmp/waystroke-mutter-sdk`。

当前收尾重点：C01 动态参数/字段引用的类型与定位、可复用编排及页面导航的原生 UI 实测；C03 逐动作剩余文件/编码/URI/应用操作检查；C05 会话/系统设置、能力注册与 69 项对应证据审计。隐藏的非活动参数不应妨碍切换操作后的保存，需同时核对 model 和 adapter。阶段 C 仍保持进行中。

### 阶段 C 增量：编排类型、超时与原生 UI（2026-10-14）

- model/adapter/执行器统一处理非活动参数：切换到四舍五入、单目条件等操作后，隐藏字段保留原绑定，但不要求已经删除的引用继续可用。重新启用该参数仍严格检查；条件比较支持变量选择器插入的字段路径，并按字段类型保存数字等比较值。
- 全宽编排和规则内步骤设置补齐公共“步骤超时”，正式 HTML 同步同样布局。原生 UI 已证明 300 ms 超时落盘、变量输出改名保持 ID、正式录制/识别/运行详情、复制/重开、断线保存保留草稿和真实退出，见 native-ui.json。
- 编排应用/保存前接入正式模型校验；错误选择对应步骤，参数与树保留。检查期间离开页面不会让异步响应覆盖另一页面。类型化数据默认值允许 JSON 对象，列表支持每行文本或 JSON 列表；命令 pid 可直接插入变量。
- 结果类型“自动”使用推断声明 Any，实际值仍保持原生 Text/Number/Boolean/List/Window/Data 类型。字段读取、JSON 和列表项可被后续合适的动作直接消费；显式指定的输出类型仍严格校验，不能把失败结果伪装为数据对象。遍历项可选择自动；工作流接口仍提供既定六种类型。真实 core 检查自动字段→数字计算成功及显式错误类型失败，见 execution-inference.json。
- UTF-16 写入必须实际编码为所选字节序，不能采用编码库返回的 UTF-8 替代；Unicode/emoji 字节与读取结果实证见 execution-encoding.json。HTTP 正文支持响应字符集，重复响应头按换行保留。D-Bus 属性设置的可选输出为服务确认的 written=true，不伪造读回值。

阶段 C 尚未完成。继续：补齐可复用编排另存/调用和页面导航的原生 UI 验收、类型推断 UI 检查、其余文件/应用/URI 与会话操作、代表性完整编排、能力注册及 69 项证据审计。上表“已接入”只表示执行路径已存在，未代替逐项验收；主会话组件仍未更新。

### 阶段 C 增量：剩余文件、可复用动作与能力注册

- 目录复制/移动保留子文件与符号链接，覆盖替换旧目录，递归筛选和全部文件信息枚举已经真实执行。GIO 不支持对 /tmp 内部挂载回收；检查将自己的源文件及私有回收站置于工作区同一文件系统后，实际回收成功且内容完整，随后清理这些临时文件。没有写用户回收站。URI 打开使用私有注册的 scheme handler，确实收到原 URI，见 execution-files-uri.json。
- 原生 UI 实际另存全部步骤为可复用动作、将规则改成 flow.call 并保存、调用真实执行成功；新进程的 --page text 通过单实例路径切换现有窗口。新增检查参数已经传入私有会话，结果明确包含这些项目，而不是仅用原有 complete 标志推断，见 native-reusable-ui.json。
- 69 项动作使用显式执行器注册映射，GetActionCapabilities 返回 available/limited/unavailable、执行器与真实原因。扩展报告当前剪贴板原生组件、音频及背光条件；旧扩展模块不冒充阶段 C 能力，目标服务/权限仍逐步校验。支持配置当前受限动作，不能把暂缺硬件当成删除功能。运行状态、动作选择器与当前参数说明已经显示能力信息，HTML 同步对应布局。
- 独立 GNOME 证明 69 项均有注册、原生剪贴板可用、无背光明确不可用；原生 UI 加能力信息后，完整保存/另存调用/导航/重开/退出仍通过，见 desktop-capabilities.json 和 native-capabilities-ui.json。注册与环境报告不等于每种操作均已逐项通过，阶段 C 尚未完成。

继续收尾：应用/命令参数与目标、实际系统设置、会话操作的安全检查、计划指定的完整代表性编排，以及 69 项逐行证据核对。主会话升级和原生组件安装仍未执行，现有用户配置及运行窗口保留。

### 阶段 C 增量：完整编排、应用与会话收尾（2026-10-14）

- 计划指定的剪贴板→文字处理→真实 HTTP POST→状态分支→遍历真实文件→GNOME 通知，以及等待窗口→查找→显式目标→文字输入，均在独立 GNOME 中完整执行，结果见 `fixtures/phase-c/desktop-integration.json`。
- 修复启动动作的窗口语义：不保存窗口且不设目标时，桌面启动请求成功即可；要求新窗口时先快照已有句柄，等待此次新窗口，不能拿旧窗口冒充。原生启动参数包含带空格参数、已有窗口激活、关闭一个/全部窗口、新窗口目标、无窗口超时与真正 GNOME 声音设置入口通过，见 `desktop-apps-session.json`。
- 会话确认取消不执行锁屏；正式 session 动作确实锁定独立 GNOME，并禁用执行。扩展锁屏事件现一次更新 locked/输入释放/执行不可用及状态原因，消除过渡状态不一致。注销和挂起仅对私有会话/系统总线服务验证 Logout(0)、CanSuspend、Suspend(true) 及权限/能力失败，见 `execution-session-contract.json`；主机只读 CanSuspend=yes，没有在用户主会话自动挂起或注销。
- 列表五种操作、停止完整嵌套序列补齐正式执行证据，见 `execution-final-data.json`。原生编排的非法循环、缺失变量及递归定位和自动结果类型引用检查已通过，见 `native-editor-final.json`。

阶段 C 仍未宣布全部完成：剩余编辑器错误定位审计、69 项证据逐行映射和主会话组件升级闭环。以上结果各自只证明注明的范围。

### 阶段 C 当前交付状态

- C01：正式模型/动态参数/类型和局部作用域已接入；原生 UI 已验证保存重开、复制引用、另存并改为调用、自动类型引用、非法循环退出、缺失变量及递归调用定位。递归错误现在指向当前编排中造成循环的调用步骤，见 `native-editor-final.json`。新增动作使用有效字面量默认值，不再自带未定义示例变量；HTML 同步默认值。
- C02：快照/FIFO/嵌套流程、接口参数与返回、有限循环控制、整序列停止、失败继续、超时和取消事件完成隔离验收；按键及剪贴板取消清理已有真实桌面证据。
- C03–C05：69 行均已映射对应执行证据；无背光明确不可用，MPRIS/音频等以实际服务或设备为条件。注销/挂起只验私有服务调用及失败，依计划不自动执行主会话破坏性操作。原生 UI、编译、模型/core 和适配器必要检查通过；锁屏拒绝新 RunRule 的隔离回归也已通过，见 `desktop-final-lock.json`。
- 主会话仍保留阶段 B 的运行窗口和配置，尚未安装剪贴板原生组件、加载当前扩展或启动当前窗口/core，阶段 C 不宣布全部完成。已向用户提供 `sudo bash scripts/install-dev-clipboard.sh`；之后需保留用户编辑并核实实际 hello 能力和 69 项注册，不能仅以磁盘文件或扩展实例变化认定升级成功。

主会话只读核对：目前 locked=true、inputArmed=false、executionAvailable=false，原因“桌面已锁定”；扩展因 GNOME 锁屏停用而不拥有总线名。没有重启窗口或修改用户配置。RunRule 因此先检查原生锁屏状态，再检查扩展连接，避免将锁屏误报成一般服务缺失。

本轮自主检查完成：锁屏实际生效、正在执行/排队取消及恢复、锁屏后 RunRule 拒绝全部通过。主会话原生组件管理员安装请求仍待用户回复，窗口和旧 core 保留；未宣称阶段 C 全部完成。

### C04 加强核对进行中：概览与焦点顺序

按“所有操作枚举正确”补齐双击、鼠标按下/释放、三种拖动、显示桌面切换及全部窗口信息/目标来源。组合检查暴露概览动画与输入目标焦点的顺序问题；新增 GNOME 显示/隐藏信号等待，并在主循环清理后完成；键盘、快捷键、文本、复制/粘贴等待明确目标聚焦，停止时清除相应等待。该轮输入枚举已执行，取消粘贴后 GTK 多 MIME 读取出现超时，正在核对，不能将当前加强检查或阶段 C 整体记为完成。管理员组件安装也仍未完成。

C04 加强核对结果：`desktop-enums.json` 完整通过双屏窗口/信息与目标来源、显示桌面切换、键鼠全部常用枚举及剪贴板恢复组合检查。概览动作等待实际 shown/hidden，并在 GNOME 模态焦点清理后的主循环完成；输入等待目标 focus-window 后再发送，剪贴板发送回调也参与等待。测试 GTK 读取改为异步，避免自身同步读管道阻塞主循环造成超时。另补滚动跨窗目标检查：指针不在指定窗口时先移到其中心；动作说明和 HTML 一致。最后跨窗滚动回归正在执行。管理员安装仍待回复，没有修改主会话窗口。

C04 本轮补齐完成：跨窗滚动的实际 GTK 全窗口捕获通过，B 内指针的滚动只进入 A；全部键鼠枚举、双屏窗口与信息枚举、显式目标、概览后顺序输入、多格式恢复和取消释放均有对应结果。`desktop-scroll-target.json`、`desktop-enums.json` 为新增证据。统一构建及 diff 检查通过；没有为未改变的 UI 重复运行整套检查。当前阶段 C 剩余主会话安装/加载闭环，管理员组件仍未安装，已提出的安装请求继续有效。

主会话升级受阻（2026-10-14）：连续三轮等待同一管理员安装步骤，系统共享库及 typelib 仍不存在；`sudo -n true` 明确返回需要密码。独立检查已完成且无未结束的检查进程需要等待，现阶段不能代用户输入管理员密码，也不为等待重复运行已通过检查。目标状态标记 blocked（需要用户协助，非完成）；用户运行已提供安装命令并回复后恢复，随后保留编辑并核实新版扩展/core 的主会话加载。

### 主会话升级恢复（2026-10-14）

用户恢复目标后核对确认剪贴板共享库与 typelib 已安装，SHA256 与当前 target/native 一致；主机 GJS 空源 factory 导入成功，未操作用户剪贴板。当前 WayStroke 窗口和 core 均未运行。扩展安装脚本已在普通用户会话执行，五个文件与仓库一致，并按用户约定 disable/enable；实际新实例 4021e4db-106f-4b32-8dbe-aec9af64f497 仍只报告阶段 B 三项能力，没有 declarativeActionsV1，因此不能认定阶段 C 已加载。证据 `host-upgrade.json`。本轮阻塞不再是管理员安装，而是当前 GNOME 已导入模块缓存：已请求用户保存其他工作、注销并重新登录；之后启动当前窗口/core 并核实实际阶段 C 能力，原目标仍 active，未宣布完成。

用户请求安全暂停并重新登录：已优雅停止项目旧后台残留 PID 833030，确认该进程退出，系统不存在 WayStroke 虚拟输入设备；当前不启动窗口、不执行动作。目标暂停，等待用户重新登录后明确继续。恢复后首先查询 hello 的 declarativeActionsV1，确认当前扩展实际加载，再启动当前窗口/core 完成阶段 C 主会话闭环。

### 主会话联通与连续粘贴修正

重新登录后的扩展实例 12742613-0efe-4cb6-bae7-3acb56ee61d9 实际包含 declarativeActionsV1。已启动当前原生窗口/core；主会话 69 项注册（63 available / 5 limited / 1 unavailable）、原生多格式剪贴板与音频输入/输出能力可用、无背光明确不可用，鼠标 inputArmed=true，原三条规则通过正式校验。实际可复用接口/自动数字/重复/Unicode 临时粘贴向专用 PhaseC A 执行，B 未输入；两次输入出现覆盖而非追加，整体验收仍未通过，见 host-session.json 的 complete=false。临时停用规则与动作已按 ID 移除，原有配置 ID 保留。

修正输入焦点处理：已有焦点就是目标窗口时，不重复 Main.activateWindow，避免 GTK 的重复激活改变选择区和光标；原本需要切窗时仍等待明确焦点。隔离连续粘贴和全部剪贴板恢复回归通过，见 desktop-serial-paste.json。hello 增加 stableInputFocus 作为该行为的实际加载标记，避免仅凭磁盘更新认定修复已加载。当前主会话尚未载入该小修复，阶段 C 仍保持进行中。

连续粘贴修复的安装后核对：重开实例 cac39760-925f-4a03-ae10-cdd0ad046d39 仍没有 stableInputFocus，实际仍使用修复前模块；core 已恢复 inputArmed=true / locked=false。已请求用户先保存 WayStroke 编辑并确认可安全暂停，再释放鼠标和退出后台后重新登录。没有主动关闭可能有未保存编辑的窗口，不将当前主会话联测失败改判通过；待加载修复标记后重跑专用窗口闭环。

用户确认“可以暂停”：已通过主会话 Core.Quit 成功退出后台，确认无 waystroke/waystroke-core 进程且无 WayStroke 虚拟输入设备。配置保留，目标暂停等待重新登录。恢复先核对 stableInputFocus 已实际加载，再重跑 /tmp/waystroke-phase-c-host-check.py 的专用窗口连续粘贴闭环，不能重复安装或把上一轮失败当成通过。

### 默认开发验证切换至 Devkit

用户要求减少主桌面注销，后续扩展/UI/编排回归使用独立 Devkit Shell、私有 D-Bus 和 XDG 配置；修改后只重启该测试实例。入口 `python3 scripts/check-gnome.py --devkit --phase-c-clipboard --phase-c-composed-input`。主桌面扩展部署集中到版本验收，不能把每次小修复当成要求用户注销的理由。

GNOME 50.5 Devkit 默认带宿主剪贴板转发，回归启动后即通过私有 RemoteDesktop.Session.DisableClipboard 禁用，避免宿主内容进入测试及额外读取伪装目标应用消费。测试启动概览显式关闭；最大化按真实 GNOME 原生状态核对，不依赖可调整 Devkit 窗口的像素增长。没有删除未读取超时或取消恢复验收。

本轮 `devkit-desktop.json` 整体通过：新实例实际 stableInputFocus、当前默认图形后端（未强制软件渲染）、69 项注册、连续粘贴保持光标、原多格式恢复/取消/未读取超时、可复用参数返回→自动数字→重复→Unicode 实际输入，另一个窗口未变化，临时条目移除，停止/锁定队列清理通过。独立配置原 ID 保留。`devkit-composed-input.json` 为该完整编排子检查。主桌面未部署或重新开启，本轮不要求注销。

Devkit 之后的主桌面只读核对：当前扩展仍是 cac39760-925f-4a03-ae10-cdd0ad046d39，没有 stableInputFocus。本轮未更新、重开或启动主桌面组件，也不要求为常规回归注销；剩余集中部署/实际加载验证仍记为未完成，开发与 Devkit 通过不冒充主桌面已加载。此前 Devkit 默认剪贴板同步可能把测试内容带到宿主，现已在入口启动阶段明确关闭此通道；后续仅私有桌面读写测试剪贴板。

### 阶段 C 完成记录（2026-10-14）

用户明确取消主桌面验证要求，以测试环境通过作为验收通过。撤销此前由开发过程附加的主会话加载完成门槛；主桌面当前模块状态保留为部署事实，不再阻塞阶段 C，也不再要求用户注销。

| 任务 | 完成依据 | 状态 |
| --- | --- | --- |
| C01 | 正式编排模型与原生 WebKitGTK 界面；保存/重开、复制稳定引用、规则另存并改为真实调用、自动类型、非法变量/循环退出/递归定位。native-editor-final.json 与适配器检查。 | 完成 |
| C02 | execution-final-data.json：不可变快照/FIFO、类型化参数返回、分支/有限循环、break/continue/整序列 stop、等待、失败继续、超时、取消与步骤事件；桌面检查证明输入释放。 | 完成 |
| C03 | 69 行逐项执行证据：实际数据/文件/目录/回收站/URI、命令直接与 Shell/等待与异步、子进程取消、HTTP/D-Bus、WayStroke 控制及实际页面导航。 | 完成 |
| C04 | desktop-enums.json、desktop-scroll-target.json、desktop-input-clipboard.json、devkit-desktop.json：显式目标、键鼠枚举、双屏/工作区、显示桌面恢复、复制拒绝旧内容、完整 MIME 恢复与取消、连续粘贴及可复用重复输入。 | 完成 |
| C05 | desktop-audio.json、desktop-system.json、desktop-apps-session.json、execution-session-contract.json、desktop-capabilities.json：实际系统动作或明确能力限制、无设置窗口的原生对话框、69 项显式注册。注销/挂起仅对私有服务验证，符合原计划。 | 完成 |

最终补齐动态参数执行语义：显示器/工作区只有“指定编号”解析编号，剪贴板截图不解析隐藏路径；缺失隐藏引用仍可执行，实际窗口操作和 PNG 输出通过。证据 desktop-inactive-window.json、desktop-inactive-screenshot.json。原生目录与 HTML 的 69 项定义逐项相等，构建与 diff 检查通过。未追加无关边界测试，未执行主桌面验证。

完整代表性编排、可复用参数返回、失败继续和用户取消已有对应测试结果。原始主会话尝试失败记录保留为历史事实，不改写为通过；当前完成结论依据被用户认可的隔离/Devkit 验收。无背光设备明确不可用，不伪造亮度执行成功；服务与权限相关动作保持实际条件检查。下一阶段为 D：真实文本替换，不属于本次完成范围。


## 阶段 E 实施记录（2026-10-15）

E01–E03 已完成。标准构建、模型/核心检查、原生向导/页面及文本回归通过并归档。接入向导已从说明弹窗改为真实安装/连接请求；管理员系统级部署及 RPM 生命周期的完整验收仍属于 F01–F03。

- E01：`crates/core/src/configuration.rs`、协议 `ConfigurationRequest / ImportPreview` 和桌面配置页接通真正的文件内容检查、导出、合并与替换。检查令牌绑定不可变内容和配置 revision；检查/取消不写活动配置。保留非冲突稳定 ID；冲突模板、动作与局部符号重建 ID，重映射主样本、规则、嵌套调用、输入参数、返回字段、变量和插值引用。只处理可复用动作返回字段的身份路径，不改写普通数据字段与用户文本。保留现有偏好、同关键词/应用文本和已有应用排除；冲突规则副本停用。未知动作、版本、悬空引用和递归均先由正式模型拒绝。
- E02：备份位于 `${XDG_STATE_HOME:-$HOME/.local/state}/waystroke/backups`，目录 0700、文件 0600。手动、导入前与恢复前备份均落盘并重新读取校验，失败阻止覆盖；最近 5 份，支持真正恢复、删除、独立导出与重启读取。迁移不携带执行记录或接入完成/授权状态；鼠标稳定身份属于偏好，正常导出并由替换/恢复采用，合并保留本机现有设置。GTK 文件对话框属于设置窗口，采用异步响应，支持取消、覆盖确认和随父窗口关闭；正式配置仍由 core 原子保存。
- E03：清除旧备份样本、运行状态模拟事件/固定任务及测试页固定 Firefox 上下文；版本号改为读取桌面包实际版本。连接断开清除旧运行快照与能力，版本不兼容显示实际原因并刷新总览/能力，不再被鼠标连接错误覆盖。保存失败恢复实际启停显示。设置中的登录启动偏好接入真实 XDG autostart 入口，完成初次设置后才生效；配置保存失败回滚登录入口，登录入口失败阻止假报保存成功。诊断导出采用版本、组件、能力、时序、执行状态/步骤 ID 白名单，不导出配置、窗口标题、步骤输出、剪贴板或替换正文。
- 运行摘要继续仅在会话内保存并有界清理（现有最多 50 条保留记录，另有最多 32 个排队项和 1 个执行中项，低于 100 条要求）；不增加记录设置项，不持久化用户命令输出或输入正文。

逐页及弹窗核对：

| 页面 / 弹窗 | 当前证据 |
| --- | --- |
| 规则、模板、编排、动作库 | Devkit 中实际录制/保存、超时、变量与返回引用重命名/复制、递归/作用域定位、来源引用/删除限制、另存并调用、真正执行与重新打开；已有 B/C 证据继续保留。 |
| 文本与文本规则弹窗 | 正式页内匹配/撤销、现有规则编辑、真实 GTK 能力、密码/停用与锁屏/解锁；阶段 D 的浏览器、终端、IME、AT-SPI 接入证据保持有效。 |
| 手势测试与选窗/执行详情 | 正式识别分值、仅预览、显式选取真实窗口后执行、实际执行详情；无固定结果/初始窗口样本。 |
| 运行状态与通用消息 | 实际任务和结果、能力、清空/停止、断连与重新取快照；测试私有扩展故意上报协议 99 后显示不兼容并禁用执行，恢复 1 后真实恢复。 |
| 配置、导入确认与错误 | 真文件摘要、取消不提交、合并冲突副本与文本保留、恢复与删除；导入规则调用动作实际写文件，导入文本立即进入正式匹配器；错误版本原配置不变。 |
| 设置、初次设置、标题栏 | 设备/缺失状态、独立文本开关/排除、真实登录入口创建/移除及通过该入口重新启动 core；向导/确认/消息、拖动、窄窗口、最大化/还原、最小化重开、未保存关闭、后台继续与真正退出。安装包、管理员授权集成和系统级发布验收仍按原 F01–F03 范围执行。 |
| 文件保存 | 配置、所选备份和诊断均通过 GTK 对话框实际保存为 JSON；取消不改配置/备份。 |

代码保留既有页面分区、类名和 CSS；未修改 `design/` 或 `style.css`。原生截图和状态结果在 `fixtures/phase-e/`，不使用 Chromium 代替 WebKitGTK。所有扩展检查均在私有 mutter-devkit 中完成，关闭宿主剪贴板转发，不选择物理鼠标，不部署或测试主桌面。

必要验证：`cargo test -p waystroke-model -p waystroke-core`（4 + 10 项）及桌面资源安装单元检查（1 项）、`npm run test:adapter --prefix apps/desktop`、`python3 scripts/check-core.py`（含无扩展时迁移/备份/恢复）、`python3 scripts/check-ui.py --devkit --phase-e --phase-c` 及 `python3 scripts/check-ui.py --devkit --phase-d` 均通过。`./scripts/build.sh` 已通过；缺失的 Mutter/graphene 开发头文件仅解包到 `/tmp/waystroke-mutter-sdk`，未安装系统软件包。原生辅助库重建前后 SHA-256 一致。最终回归使用标准构建产物，源码/二进制哈希和验收范围见 `fixtures/phase-e/source.json`、`verification.json`。


阶段 E 收尾：`apps/desktop/src-tauri/src/setup.rs` 将扩展资源嵌入桌面程序，检查实际 GNOME 版本，经 Extensions D-Bus 请求启用已安装扩展；首次安装写入真实用户扩展目录并明确提示 GNOME 50.5 需要重新登录，不假报连接成功。鼠标操作封闭调用 `pkexec` 与 `packaging/setup-input.sh`，不接受前端提供的命令、路径或 UID；授权 UID 取自 `PKEXEC_UID`，服务安装保持空闲、不启用开机服务。取消/拒绝可重试，按钮的就绪状态仅取真实 core 连接快照。运行状态的“完成鼠标授权”打开对应向导步骤；开发/发布构建同时准备配套 inputd。

新向导验证仍全部在私有 mutter-devkit：实际禁用/重新启用扩展、卸载私有副本后从按钮重新安装 7 个正式资源并显示重新登录边界；授权启动器夹具先返回 pkexec 的取消码 126，再以普通用户运行实际安装脚本，将二进制、服务单元与 UID 配置安装到临时前缀并检查内容及 0600 权限。未连接真实 inputd 时界面仍显示未就绪。测试没有执行主系统 systemctl、管理员认证或主桌面扩展操作；真实 root 路径拒绝测试前缀，完整系统部署保留 F 阶段门槛。`source.json` 分别记录首次加载的测试扩展与重新安装后的磁盘资源哈希。

## 阶段 F 实施记录（2026-10-16，已完成；实物拔插验证由用户明确跳过）

| 项目 | 当前实现及验证 | 最终状态 |
| --- | --- | --- |
| F01 | `scripts/build-rpm.sh` 与 `packaging/rpm/waystroke.spec` 生成 Fedora44 release RPM；3 个正式可执行文件、系统/用户 systemd 单元、会话 D-Bus 激活、desktop 入口、扩展和原生剪贴板资源。固定 root helper 与 polkit 策略只授权鼠标服务，UID 取 `PKEXEC_UID`。实际 DNF 安装保持服务未启动/未启用、无授权与登录入口；策略解析、非活动会话拒绝无副作用、取消重试 UI、UID/0600 配置及 root helper 通过。实际安装窗口能激活 core，关闭后后台继续、重开复用；登录偏好及无接入编辑通过原生 UI/会话检查。 | 设备授权、当前系统扩展实际加载、选定 G304 接管和真实手势执行已通过。授权后开机恢复修复及验收通过。 |
| F02 | Devkit 双屏 1.0/1.25 缩放、桌面/真正 GTK 瞬态窗口/未聚焦起点、窗口与工作区动作、反馈位置；扩展重启旧句柄失效与队列取消、锁屏取消及解锁；core SIGTERM 与重开配置保留通过。真正 GNOME/core/root inputd 容器联测证明停止服务取消运行/排队任务、释放实际按住的 Shift，恢复后重新连接。文本和手势开关独立。 | 完成其余集成验收及主机真实手势最大化。2026-10-16 用户明确要求跳过接收器拔插测试，实物热插拔与拔插后恢复仍未验证，不标为通过。 |
| F03 | 最终 release 构建，RPM 1→2 实际升级/卸载、停止组件、移除系统文件、保留用户配置/备份通过；已知旧开发 inputd 单元迁移，正式服务与 probe 互斥。RPM 内 3 个程序、7 个扩展和 2 个原生资源逐项摘要一致。最终 WebKitGTK 八页、编排、向导、文件、标题栏、保存/重开/退出及真实安装路径启动通过；历史 A–E 功能证据继续对应未改变的实现。正式启动不依赖 probes、样本配置或测试服务。 | 完成。当前 release 2 主机安装及摘要/所有权核对通过；F02 实物拔插验证按用户最新指令豁免。 |

本阶段修复：无鼠标租期时扩展断连未取消任务；inputd EOF 残留待完成轨迹/队列；core 缺少 SIGTERM 清理；异步保存返回后覆盖已导航页面；混合缩放字体度量变化后反馈偏移；文本输入队列在无绘制帧时等待未受服务，以及保存配置清空同焦点排队的用户输入。后两项已用持有真实 RPC 的配置/焦点专项及无诊断注入回归验证，旧焦点请求仍取消，同焦点 `abcxyz` 完整送达。core/IBus 断连和锁屏恢复、Ptyxis/VTE 与 XWayland GTK 必要回归通过。修复前失败记录保留，当前结果以最终证据为准。

证据、受测范围与重跑方法见 `fixtures/phase-f/README.md`、`verification.json`。常规扩展、文本和 UI 使用私有 mutter-devkit，不部署主桌面，不选择物理鼠标。RPM/systemd/inputd 在 rootless Fedora44 容器；空闲 `/dev/uinput` 夹具不冒充真实抓取。安装路径启动最终在只读 RPM `/usr` 文件覆盖层与 Devkit 完成，私有 `/dev` 不绑定宿主设备；实际画面已核对。容器中的图形沙箱/线程资源失败保留为环境事实，不冒充通过。当前可独立完成的软件工作已通过，剩余需要管理员授权及真实鼠标操作；没有把该缺口降格为优化项。

阶段 F 阻塞核对：同一管理员/实机条件已连续三轮存在。当前源码及发布产物摘要与最终验证一致；软件结果仍通过，测试容器均已停止。宿主未安装 WayStroke RPM，inputd inactive，core 未运行，`sudo -n true` 明确要求密码。可自主完成的工作已经结束，剩余管理员安装/鼠标授权，以及接管期间真实拔出、重插和恢复操作，需要用户协助；不是阶段 F 完成。用户安装已验证 RPM 后继续核对实际加载版本与设备闭环，必要时才集中处理扩展加载。

主机会话安装恢复：用户安装 `waystroke-0.1.0-1.fc44.x86_64` 后，`rpm -V` 及 3 个程序摘要全部通过；已启动正式窗口及 `/usr/lib/systemd/user/waystroke-core.service`，登录入口已采用安装版服务。原有 3 条规则、1 个模板和全部稳定身份保留。发现 GNOME 实际加载的仍是用户目录旧副本，`textStatus` 明确不支持；已将该副本完整备份到用户 state/waystroke/deployment，移开对系统扩展的遮蔽，系统 7 个资源与受测源码逐项一致。当前 Shell 的缓存不会因移开文件而更新，下一次 GNOME 会话才加载安装版。

为保证授权期间不抓取鼠标，已临时保存 gesturesEnabled=false（revision 29），记录原值 true 待验收后恢复；inputArmed=false。已通过正式 polkit 动作发起固定鼠标服务授权，当前进程仍在等待桌面管理员认证，服务 inactive。需要用户先完成桌面认证，再保存并退出 WayStroke/其他工作、注销重新登录一次；恢复后继续核对实际模块、授权/设备和热插拔闭环。窗口保留供用户保存可能的编辑，没有擅自关闭或注销会话。记录 `fixtures/phase-f/host-session.json`。

主机会话恢复后的阻塞核对（2026-10-16）：同一桌面认证/新会话条件已连续三轮存在。原 pkexec 认证进程仍存活且未返回，inputd inactive，inputArmed=false；当前 Shell 仍不支持正式 textStatus，尚未加载系统扩展。没有重复发起认证、重启组件或擅自注销。可自主准备的安装、入口、资源及旧副本备份已完成；目标重新标记 blocked，等待用户完成桌面认证，保存并退出 WayStroke/其他工作后注销重新登录，再恢复验证。手势临时暂停和恢复原值的记录保留。


阶段 F 重启恢复修正（2026-10-16）：主机实际重启后发现已授权 inputd 未启用开机启动，导致 core 登录启动而鼠标服务缺失。固定 helper 改为 `enable --now`，RPM 升级仅对已有授权迁移启动偏好；首次安装仍不授权、不启动接管。release `0.1.0-2.fc44` 已实际安装且 `rpm -V` 通过，服务 active/enabled，当前 GNOME 已加载系统扩展正式文本接口。真实 systemd 容器重启证明已授权服务自动恢复且保持 idle，卸载移除启动链接并保留用户数据，见 `rpm-boot-recovery.json`。三个程序及七个扩展文件与已验收 release 摘要一致，见 `rpm-boot-fix-payload.json`。此前管理员认证和旧会话阻塞已解除；选定 G304 已接管，专用 GTK 窗口与限该窗口的临时最大化规则正在等待实物拔插/点击/手势验收，尚不宣告 F 完成。


阶段 F 最终收尾（2026-10-16）：本条替代上述历史阻塞/等待结论。用户明确指示“跳过重插接收器的测试。我不方便插拔”，据此取消该人工验收要求；实物热插拔没有执行、没有标记为通过。其余 F01–F03 和九项发布门槛按既有正式实现、Devkit/真实原生应用、RPM 生命周期及当前主机部署证据完成核对。主机实际 G304 接管、正式识别匹配和专用 GTK 窗口最大化成功；root 服务 active/enabled，release 2 的 `rpm -V` 在主机 UID/GID 视图无差异。临时窗口规则已移除，完整配置摘要与测试前一致，原手势开关 true 已恢复，专用测试进程及容器已停止。最终索引 `fixtures/phase-f/verification.json` 明确保留用户豁免；`host-session.json`、`hotplug-live.json`、`hotplug-client-final.json` 保存实际执行与配置恢复证据。阶段 F 在此明确豁免下完成，没有把未执行的拔插测试作为通过证据。
