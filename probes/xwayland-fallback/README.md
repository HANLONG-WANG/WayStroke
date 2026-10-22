# XWayland 无编辑接口应用的回退路径验证

仅用于技术验证，不是正式适配器。只使用专用测试窗口和固定测试文本。

运行（需要 mutter-devkit、PySide6、Tk、JDK、xterm、python3-xlib；Chrome/Code 部分使用本机已安装程序和临时配置目录）：

```sh
python3 probes/xwayland-fallback/run.py                 # 全部（wechat 需显式指定）
python3 probes/xwayland-fallback/run.py --only=layer2   # 也可选 layer1、visual、browsers，逗号分隔；wechat 必须显式指定
```

运行器创建临时 XDG 目录、私有 D-Bus 和私有 AT-SPI 总线，启动带 XWayland 的 Devkit GNOME Shell，并复用 `probes/gnome50` 的探针扩展（运行时追加批量按键、第二虚拟键盘和焦点信息接口）。只为这个一次性 XWayland 设置 `XWAYLAND_NO_GLAMOR=1`，避免 NVIDIA 下截图停在旧帧；不修改主桌面。结束时终止全部测试进程，结果与日志留在打印出的临时目录。

- `apps.py`：Tk、复制选区专用 Tk（`copy-only`，窗口类 WeChat，关闭 PRIMARY 导出，仅普通字段 Ctrl+C 导出选中内容）、Qt（xcb）、GTK4 的普通字段与密码字段，通过文件接收命令并报告字段内容。
- `Swing.java`：相同协议的 Swing 字段。
- `rawtty.py`：在 xterm 中记录程序实际收到的字节。
- `run.py`：XWayland 辅助客户端（XI2 raw 按键、XFixes 选区通知、PRIMARY/CLIPBOARD 读写）与全部检查。
- `results.json`：最终记录。完整运行的 Devkit 截图会停在早期帧，`visual` 与 `browsers` 两项分别取自单独的视觉运行和延长 Code 启动等待后的复测（见文件内说明）。
- `visual-selection.png`：Tk、Qt、Swing 替换前、校验选区保持时与替换后的窗口截图。

结论见 [技术验证第五阶段](../../docs/technical-validation.md#第五阶段xwayland-无编辑接口应用的回退路径)。


`--only=wechat` 启动 `/opt/wechat/wechat`，使用临时 HOME/XDG/总线/显示并关闭 devkit 剪贴板转发，只观察未登录界面与窗口类。登录界面没有聊天输入框，故不声称实测了微信聊天选区。随后比较正常 Qt 和 `copy-only` 夹具：150ms 与累计 1s 后的 PRIMARY/CLIPBOARD 所有权及文本、Ctrl+C 后的读回。复制选区夹具依据用户报告的“PRIMARY 未更新”失败分支构造，用于验证修复机制，不代表所有微信版本内部实现。正式替换和所有格式恢复由 `scripts/check-gnome.py --devkit --release --phase-d-atspi --selection` 验证。

本机 NVIDIA 若在 XWayland 初始化时崩溃，可为上述命令添加 `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json`（仅影响探针进程）。
