# XWayland 无编辑接口应用的回退路径验证

仅用于技术验证，不是正式适配器。只使用专用测试窗口和固定测试文本。

运行（需要 mutter-devkit、PySide6、Tk、JDK、xterm、python3-xlib；Chrome/Code 部分使用本机已安装程序和临时配置目录）：

```sh
python3 probes/xwayland-fallback/run.py                 # 全部
python3 probes/xwayland-fallback/run.py --only=layer2   # 也可选 layer1、visual、browsers，逗号分隔
```

运行器创建临时 XDG 目录、私有 D-Bus 和私有 AT-SPI 总线，启动带 XWayland 的 Devkit GNOME Shell，并复用 `probes/gnome50` 的探针扩展（运行时追加批量按键、第二虚拟键盘和焦点信息接口）。只为这个一次性 XWayland 设置 `XWAYLAND_NO_GLAMOR=1`，避免 NVIDIA 下截图停在旧帧；不修改主桌面。结束时终止全部测试进程，结果与日志留在打印出的临时目录。

- `apps.py`：Tk、Qt（xcb）、GTK4 的普通字段与密码字段，通过文件接收命令并报告字段内容。
- `Swing.java`：相同协议的 Swing 字段。
- `rawtty.py`：在 xterm 中记录程序实际收到的字节。
- `run.py`：XWayland 辅助客户端（XI2 raw 按键、XFixes 选区通知、PRIMARY/CLIPBOARD 读写）与全部检查。
- `results.json`：最终记录。完整运行的 Devkit 截图会停在早期帧，`visual` 与 `browsers` 两项分别取自单独的视觉运行和延长 Code 启动等待后的复测（见文件内说明）。
- `visual-selection.png`：Tk、Qt、Swing 替换前、校验选区保持时与替换后的窗口截图。

结论见 [技术验证第五阶段](../../docs/technical-validation.md#第五阶段xwayland-无编辑接口应用的回退路径)。
