# 阶段 C 当前验证证据

阶段 C 尚未完成。每份结果中的 complete 仅指该检查的范围，不表示 C01–C05 或全部 69 项已完成。

- `execution-io.json`：`scripts/check-execution.py` 的真实 core/私有 D-Bus 检查。桌面 fixture 只提供握手与输入清理空接口，不产生编排执行结果；执行、局部作用域、调用/返回、循环/退出/继续、超时、取消、排队快照、配置启停、临时目录文件、真实命令与子进程组、HTTP 服务、类型化 D-Bus 服务/属性均由正式代码执行。
- `desktop-windows.json`：`scripts/check-gnome.py --multi-monitor --phase-c-window` 的独立 GNOME 50.5 双屏真实窗口检查，包含窗口状态/操作、百分比几何、显示器/工作区、查找/目标路由和显示桌面恢复。不是实体鼠标验证，不代表键鼠和剪贴板动作完成。
- `clipboard-source.json`：原生多 MIME SelectionSource 的 GJS 读取检查；Unicode 文本、HTML 和二进制字节准确保留。尚未证明应用粘贴、选中文本或临时恢复的端到端行为。

最近失败的原生输入检查目录为 `/tmp/waystroke-desktop-check-v3pd4scv`：ASCII/Shift 实際输入成功，但当前布局不存在中文/emoji 键码，Mutter 发出警告且没有输入；不得将执行器的成功状态算作 Unicode 输入成功。已加入原生文本提交/明确能力失败路径，剪贴板接入继续实施，最终输入验收仍待完成。

后续已归档：

- `desktop-input-clipboard.json`：独立 GNOME/GTK 真正收到的键鼠与 Unicode 文字、全部原 MIME 恢复、应用读取确认、复制拒绝旧内容与取消恢复。
- `desktop-system.json`：实际 Shell 模态询问和输入、通知、三种范围的 PNG 截图和取消、无背光能力报告；设置窗口不必打开。
- `desktop-audio.json`：私有 PipeWire/Pulse 的真实虚拟输出与虚拟输入，六种操作在每个设备上由 pactl 核对；WirePlumber 仅 policy profile，不连接用户硬件设备。
- `execution-io-media.json`：扩展了真实标准 MPRIS fixture，核对全部八种操作、Seek 正负微秒和能力拒绝。只证明接口契约，不代替每个用户播放器的硬件/功能保证。

前述 Unicode keyval 失败是已修复路径的历史记录；新的正向证据见 desktop-input-clipboard.json。所有检查都在私有总线/桌面进行；主会话仍运行原版本，原生组件安装和正式 UI 收尾尚待完成。

- `native-ui.json`：真实 WebKitGTK/Wayland 窗口的完整配置/录制/执行/重开检查，含编排超时保存与异步正式模型校验后的另存弹窗；实际“另存并调用”完整行为仍待补齐，不以打开弹窗替代。
- `execution-encoding.json`：UTF-16LE 的真实磁盘字节及 Unicode 读回，并包含原有 core/I/O 检查。
- `execution-inference.json`：自动字段结果通过实际类型进入后续数字计算，显式声明错误类型仍失败；与其他 core/I/O/MPRIS 检查一起完成。它不代表自动类型在全部 UI 入口已验收。

- `execution-files.json` / `execution-files-uri.json`：完整目录复制/移动、符号链接、覆盖、递归筛选、全部文件信息、实际私有回收站与真实私有 URI handler。源文件和私有回收站的工作区临时目录已清理；用户回收站不变。
- `native-reusable-ui.json`：正式另存步骤为动作、规则改为调用并保存、实际执行包含调用及子步骤；通过原生单实例参数导航到文本页。
- `desktop-capabilities.json` / `native-capabilities-ui.json`：69 项显式注册与当前环境限制，及展示能力后的原生 UI 流程。每项的注册字段不代替动作效果验收。
