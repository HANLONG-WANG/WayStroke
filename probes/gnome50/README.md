# GNOME 50.5 接口验证

仅用于开发前验证，不是正式后端。源码与结果仅涉及专用测试窗口及固定测试文本。

运行：

```sh
WAYSTROKE_TEST_IME=rime python3 probes/gnome50/run.py
```

要求已有 GNOME Shell 50.5、GJS、Python GI、GTK4、IBus 和 Rime。去掉环境变量可跳过实际 Rime 验证。

运行器创建临时 XDG 目录与私有 D-Bus，启动 headless Wayland Shell（不启动 XWayland）、两个 GTK 窗口和临时输入法。它不会安装扩展到主桌面、修改主桌面配置、访问真实鼠标、获取管理员权限或执行用户配置的动作。测试结束终止测试进程，结果与日志留在打印出的临时目录中。扩展拒绝在运行器之外启用。

`extension.js`：测试实例中的窗口、虚拟输入、Stage 计数、IME 接口和截图探针。

`client.py`：两个 GTK 文本/密码字段与鼠标测量区域。

`run.py`：顺序驱动测试，记录正向与反向证据。

`results-50.5.json`：本轮最终记录，包含12个证据检查；其中“不满足需求”的结果也是有效技术结论，不代表功能通过。

完整结论与未验证项见 [技术验证](../../docs/technical-validation.md)。

## 起点窗口与真实鼠标联动

更新输入验证服务，并安装 Fedora 官方 `mutter-devkit` 预览工具：

```sh
sudo bash /home/hubery-fedora/Projects/WayStroke/probes/gnome50/install-binding.sh --user "$(id -un)"
```

安装不会接管鼠标或设置开机启动，也不在主桌面安装扩展。解锁后以普通用户运行：

```sh
python3 /home/hubery-fedora/Projects/WayStroke/probes/gnome50/binding.py --device /dev/input/event3 --seconds 60
```

如果设备编号变化，先通过已安装的 `client.py devices` 确认。新窗口显示独立 GNOME 测试桌面。仅在这个窗口内测试：

1. 左键点击 Probe B，让 B 获得焦点。
2. 把指针移到 Probe A 的内容区域，按住右键绘制到 B，然后松开。
3. `start` 应报告 title=Probe A、focus=Probe B；`finish` 应保持相同 stableId/title，并显示 endTitle=Probe B。
4. 普通右键点击仍应透传。Ctrl+C、关闭预览窗口或到时结束验证，恢复鼠标。

不能用此工具验证主桌面窗口：测试扩展只知道独立桌面的坐标和窗口。真实鼠标到预览窗口、再到独立合成器仍有转发延迟，因此需要人工核对以上结果，不能以模拟检查替代。

输入服务协议 v2 在右键开始后暂存后续事件，待窗口快照确认后继续转发；握手超过 250ms 则释放设备。此时间是探针看门狗，不是产品延迟承诺。控制器检测主桌面锁屏后停止（轮询间隔 0.5s）；启动时锁屏会直接拒绝真实鼠标验证。

不接管真实鼠标的时序检查：`python3 probes/gnome50/binding.py --self-test`。它使用真实独立 GNOME 与模拟输入事件，验证通知延迟时不会把起点 A 误取成终点 B。

## 应用文本接口验证

`stage2.py` 使用 Firefox 临时配置、Code 临时用户目录和 Ptyxis 专用输入接收脚本。终端接收内容不会作为 shell 命令执行。Ptyxis 通过宿主用户 systemd 创建临时 scope；没有修改常驻服务配置。

保存的结果分别记录浏览器/Code、终端原始输入及终端行编辑替换。Ptyxis 不提供 surrounding text，退格后提交的行编辑示例成功不代表任意终端程序、密码输入或全局关键词监听已经支持。

### 补充接口检查

以 `WAYSTROKE_STAGE2_CASES` 选择单项，避免重复整套测试。例如：

```sh
WAYSTROKE_STAGE2_CASES=firefox-extra python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=electron python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=electron WAYSTROKE_NATIVE_IME=default python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=code-extra python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=terminal-password python3 probes/gnome50/stage2.py
XWAYLAND_NO_GLAMOR=1 WAYSTROKE_STAGE2_CASES=xwayland python3 probes/gnome50/stage2.py
```

Electron 检查复用 `/usr/share/code` 的已安装运行时，复制二进制至临时目录并创建专用 resources/app；原安装不变。只有测试页面接收输入，不开启 Node renderer 集成。默认模式只指定 Wayland，不额外指定 IME 参数；另一模式显式开启 text-input-v3。两种结果均保留。

终端密码脚本只记录固定测试字符串的长度与自身终端回显状态。XWayland 的独立 headless GPU 路径遇到 NVIDIA EGL 崩溃，软件渲染模式用于验证接口；不修改主桌面设置，不据此判断主桌面的 XWayland 也有故障。

## 第三阶段文字适配器探针

仍只使用独立会话，不需重装 root 鼠标服务。相关入口：

```sh
XWAYLAND_NO_GLAMOR=1 WAYSTROKE_STAGE2_CASES=a11y-auto python3 probes/gnome50/stage2.py
XWAYLAND_NO_GLAMOR=1 WAYSTROKE_STAGE2_CASES=a11y-ime python3 probes/gnome50/stage2.py
XWAYLAND_NO_GLAMOR=1 WAYSTROKE_STAGE2_CASES=a11y-accelerator WAYSTROKE_ACCEL_IME=1 python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=a11y-accelerator WAYSTROKE_A11Y_BACKEND=wayland WAYSTROKE_ACCEL_IME=1 python3 probes/gnome50/stage2.py
WAYSTROKE_STAGE2_CASES=terminal-zle python3 probes/gnome50/stage2.py
```

`accessibility.py` 检查专用窗口中的焦点文本/密码角色，并可执行固定 abc→2003 示例。`accessibility-watch.py` 提供固定空格规则的自动文本事件示例。它们只连接私有无障碍总线，不作为全局匹配器。

`a11y-accelerator` 通过临时 GNOME 扩展保留 Enter，验证替换发生在应用 activate 之前、密码跳过、未匹配文字正常确认，以及当前 Rime 的组合保护。原生与 XWayland 的重放路径不同，具体证据和限制见技术验证文档。

`terminal-zle.zsh` 只在临时 Zsh 的 vared 行编辑器中测试 widget，不加载个人配置、安装 Shell 插件或执行输入行；对 read -s 和外部 getpass 的固定测试只保存长度。ZLE 接入的产品范围尚待决定。

`accessibility-enter.py` 和 `ibus-composition.py` 保留未采用路径的反向证据：旧式键盘监听注册失败；IBus 信号订阅不足以判断 GTK 当前同步组合状态。不能以这两个程序无异常启动就认定接口满足需求。

## 第四阶段通用终端路径

```sh
WAYSTROKE_STAGE2_CASES=terminal-generic python3 probes/gnome50/stage2.py
```

用户允许终端密码参与替换后，`terminal-monitor.js` 在独立 Shell 中验证固定 abc→2003 的输入跟踪/确认。`terminal-generic.py` 依次测试普通、Readline、getpass、Rime 和 raw 场景，不执行输入行，密码结果只记录长度及预期匹配布尔值。

本机 VTE 的一次文本提交携带 DEL×3 与替换内容，避免文本提交抢在模拟退格之前。常见行编辑及密码场景通过；raw 程序收到控制字节却不编辑，属于不可直接推广的反向证据。不要把本探针当作已完成的终端通用引擎，也不要在主桌面直接加载这份测试扩展。
