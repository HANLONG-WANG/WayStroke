# 鼠标输入服务：安装与实机验证

这是 GNOME 50.5 开发前验证工具，不是完整 WayStroke 后端。尚未在真实鼠标上完成验证；安装后通过以下流程取得证据。

## 安装

在普通桌面用户的终端运行：

```sh
sudo bash /home/hubery-fedora/Projects/WayStroke/probes/input/install.sh --user "$(id -un)"
```

安装脚本从 Fedora 官方软件源安装缺少的 `python3-evdev`，将服务程序复制到 `/usr/local/lib/waystroke-input-probe/`，写入系统级 systemd 单元和包含允许用户 UID 的配置，启动服务。只有缺少 uinput 时才加载该内核模块。

安装后默认空闲，未抓取鼠标，不设开机启动。没有修改设备权限、udev 规则、GNOME 扩展、密码输入设置或用户组。UI/控制器以普通用户运行。

## 验证

先列出符合条件的鼠标接口：

```sh
python3 /usr/local/lib/waystroke-input-probe/client.py devices
```

当前机器的设备能力检查发现 Logitech G304 位于 `/dev/input/event3`。设备号可能在重启、插拔后变化，以 `devices` 输出为准。G304 在同一接口声明键盘宏，验证工具支持该情形：宏键按来源原样透传，不参与手势，不记录文本；独立键盘不被读取事件流。

选择列出的鼠标并运行 60 秒验证：

```sh
python3 /usr/local/lib/waystroke-input-probe/client.py watch /dev/input/event3 --seconds 60
```

启动前松开所有鼠标按钮。测试期间：

1. 在测试应用中普通右键点击：应正常出现菜单，终端显示 `"result": "click"`。
2. 按住右键移动再松开：应保持指针移动，终端显示 `"result": "stroke"`，应用不收到右键、也不执行任何动作。
3. 手势中按下侧键再松开，测试辅助键事件是否被消耗、记录是否包含对应按钮；未按住右键时侧键仍按原行为工作。
4. 普通左键、中键、滚轮和指针速度应正常；特别关注虚拟鼠标是否引起速度变化。
5. Ctrl+C 结束后，鼠标应立即恢复原行为。也可等待 60 秒自动结束。关闭控制器连接后最多 3 秒自动释放。

这一步只区分“点击”和“移动轨迹”，阈值是 24 个原始 evdev 相对移动计数，不是屏幕像素，不是最终手势识别阈值。它不做相似度匹配，不绑定窗口，不识别 Esc，不运行命令，不生成屏幕轨迹。此限制仅针对技术探针，不缩减产品规格。运动与滚轮透传；有效轨迹消耗右键及手势期间辅助鼠标按钮。原本已按住其他鼠标键时开始右键操作，则原样透传，不作为手势。

结果仅包含点击/轨迹、相对移动总长与净位移、帧数、辅助鼠标按钮码，不记录应用内容。暂不自动写结果到磁盘；可回报终端结果与右键菜单实际行为。

## 停止与卸载

另一个终端可随时主动停止验证：

```sh
python3 /usr/local/lib/waystroke-input-probe/client.py stop
```

需要从系统层面停止时：

```sh
sudo systemctl stop waystroke-input-probe.service
```

完整卸载：

```sh
sudo bash /home/hubery-fedora/Projects/WayStroke/probes/input/install.sh --uninstall
```

卸载停止服务，删除其单元、配置和已复制程序。依赖包 `python3-evdev` 保留，不修改系统其他输入软件。服务不写本地字节码缓存。

## 实现与已完成检查

服务仅接受 devices/status/arm/poll/disarm。控制 socket 为授权用户所有、0600，使用 Linux SO_PEERCRED 校验 UID；不提供任意输入注入、执行命令、配置任意文件路径的接口。接管必须明确选择 `/dev/input/eventN` 的相对鼠标，有独占访问与 uinput 转发；默认没有打开任何设备事件流。错误、断开、超时、设备拔出与服务退出都会关闭设备 fd，解除 EVIOCGRAB。

systemd 限制读写系统目录和设备访问，不使用 root pip 安装。程序本身是 root 所有，普通用户不能通过更改仓库中的代码修改已安装服务。

已完成：四个路由检查（点击重放、轨迹与辅助键消耗、停止时释放按钮、游戏鼠标宏透传）；控制 socket 通信、非法路径/未知操作拒绝、连接租期到期释放；Python 编译检查、安装脚本语法检查、systemd 单元静态验证。测试采用临时解包的 Fedora python3-evdev 1.9.3，不向宿主 Python 安装依赖。

未完成：真实 evdev/uinput 链路、Mutter 的虚拟设备识别与指针加速度、物理鼠标菜单行为、实际热插拔。必须在安装后核对，不能把本页代码检查视为实机通过。

## G304 设备识别修正

首次安装后设备列表为空的根因：G304 除相对 X/Y 外，还声明 `ABS_VOLUME`，旧筛选把所有 EV_ABS 都当作绝对指针设备而拒绝。现仅拒绝绝对 X/Y 与多点触摸位置轴；非位置绝对轴保留能力并原样透传。加入了 G304 音量轴通过与绝对指针拒绝的两项回归检查；列表也显示候选被排除的原因。

修改项目源码后，需要重新运行原安装命令，把 daemon/routing/client 同步到 root 所有的安装目录并重启空闲服务。代理无法使用无密码 sudo 完成这一步，由用户在终端执行。

## 实机验证与输出延迟

G304 实机验证已反馈通过：点击菜单正常、绘制时右键被消耗、辅助组合、指针手感及超时恢复正常。此结果不代表正式识别器和动作执行器已实现。

最初控制器每 400 毫秒拉取一次结果，因此可观察到松开后约 0.5 秒才显示。新版控制器改为每 20 毫秒拉取；服务在松开事件中直接生成记录。尚未测量正式动作的端到端时延。

只更新控制器时可直接使用项目中的文件，无须管理员重新安装：

```sh
python3 /home/hubery-fedora/Projects/WayStroke/probes/input/client.py watch /dev/input/event3 --seconds 60
```
# 起点窗口握手

协议 v2 的可选 `bind_start` 模式仅供 `probes/gnome50/binding.py` 联动验证使用：右键开始产生 begin，暂存后续鼠标事件，收到对应 sequence 的 bound 后继续。确认超过 250ms 自动释放设备。默认 watch 模式无需握手。升级需要重新运行安装脚本；安装后仍保持空闲。

