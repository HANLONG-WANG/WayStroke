# WayStroke 开发与构建

普通使用、安装及功能介绍见[项目首页](../README.md)。日常使用推荐安装 RPM，开发与常规回归优先使用独立 mutter-devkit 会话，避免开发扩展覆盖主桌面的正式版本。

当前目标环境为 Fedora 44、GNOME Shell / Mutter **50.5**、Wayland、x86_64；不保证其他版本可编译或运行。

## 构建准备

需要 Rust／Cargo、Node.js／npm、C 编译器和 `pkg-config`，以及 Tauri/WebKitGTK（≥ 2.46）、Mutter 原生组件的开发依赖。相关开发包包括：

```bash
sudo dnf install webkit2gtk4.1-devel gtk3-devel librsvg2-devel \
  mutter-devel graphene-devel rpm-build glib2-devel
```

开发包必须与目标桌面的 ABI 匹配：`mutter-devel` 与已安装的 `mutter` 版本一致（原生剪贴板组件调用了 Clutter 私有构造函数，构建脚本会核对）。Fedora 中 `mutter-devel` 要求同版本 `mutter`，安装时可能连同 `mutter`、`mutter-devkit` 一起升级；安装前核对软件源版本，GNOME Shell 仍须为 50.5。Mutter 50.6 与 50.5 的安装头文件完全相同，只含显示器旋转与工作区修复。`mutter-devkit` 是独立桌面测试工具，不能替代 `mutter-devel`。

原生组件构建前可以检查：

```bash
pkg-config --modversion libmutter-18 graphene-gobject-1.0
command -v cc gi-compile-repository rpmbuild
```

也可以将对应版本的 Mutter／graphene 开发 RPM 解包到独立 SDK 目录，再通过 `WAYSTROKE_MUTTER_SDK=/绝对路径/SDK` 指定。该目录应包含解包后的 `usr/include/`、`usr/lib64/pkgconfig/` 等结构。历史构建使用过 `/tmp/waystroke-mutter-sdk`；它是临时目录，不应被视为已安装的系统依赖。

安装前端依赖：

```bash
npm ci --prefix apps/desktop
```

## 构建 RPM

在仓库根目录执行完整构建：

```bash
bash scripts/build-rpm.sh
```

脚本依次构建原生剪贴板组件、release 后台和桌面程序，再打包扩展、原生资源、systemd 单元、D-Bus 激活和安装授权 helper。当前默认产物：

```text
target/rpm/RPMS/x86_64/waystroke-0.1.0-2.fc44.x86_64.rpm
```

同一软件版本继续修改时，递增 RPM 修订号，避免新旧包使用相同版本标识：

```bash
WAYSTROKE_RPM_RELEASE=3 bash scripts/build-rpm.sh
sudo dnf upgrade ./target/rpm/RPMS/x86_64/waystroke-0.1.0-3.fc44.x86_64.rpm
```

`--skip-build` 仅重新打包现有 `target/release/` 和 `target/native/` 产物；修改源码后不要用它代替完整构建。发布新的软件版本时，同步 `Cargo.toml` 的工作区版本、`apps/desktop/src-tauri/tauri.conf.json`、前端 `package.json`／锁文件及 RPM spec 的 `Version`，再更新锁文件和变更记录。

构建普通用户运行，不要用 sudo 编译。正式安装、升级、扩展缓存和卸载行为见[安装说明](../packaging/README.md)。

## 开发运行

```bash
./scripts/build.sh
./target/debug/waystroke
```

窗口会启动同目录的 `waystroke-core`。关闭设置后后台继续，运行状态页的“退出 WayStroke”停止窗口与后台。

前端热更新：

```bash
npm run dev --prefix apps/desktop
```

该命令先生成类型并构建 debug 后台。主桌面有正式 core 时，不要直接混用开发后台和正式配置；测试入口会使用独立总线与 XDG 目录。

主桌面开发安装入口仍保留：

```bash
sudo bash scripts/install-dev-input.sh --user "$(id -un)"
bash scripts/install-dev-extension.sh
sudo bash scripts/install-dev-clipboard.sh
```

这些命令会修改系统或用户安装路径，仅在确实需要主桌面开发接入时使用。用户目录扩展会覆盖 RPM 扩展；原生库安装路径与 RPM 重叠。已有正式 RPM 时，优先独立测试，切勿直接运行开发卸载脚本清理正式安装。GNOME 缓存导入模块，扩展代码更新后需要新会话。

## 必要检查

按实际改动选择相关检查，不必为文档或局部修改重跑全部桌面验收：

```bash
cargo test -p waystroke-model -p waystroke-core -p waystroke-inputd
npm run check --prefix apps/desktop
npm run test:adapter --prefix apps/desktop
python3 scripts/check-core.py
```

原生 UI 与桌面集成检查：

快捷键捕获由 Tauri 的 `capture_shortcut` 使用独立会话 D-Bus 连接直接调用 GNOME 扩展，避免占用 core 的动作处理循环。扩展使用模态键盘抓取并临时过滤系统快捷键，松开全部按键后返回现有快捷键字符串；连接消失、锁屏、扩展停止及超时均结束捕获。`--shortcut-capture` 在私有桌面验证捕获、取消、连接退出清理、保存回填及实际发送。

```bash
python3 scripts/check-ui.py --application-scope
python3 scripts/check-ui.py --rule-filter
python3 scripts/check-ui.py --ime-shortcuts
python3 scripts/check-ui.py --shortcut-capture
python3 scripts/check-ui.py --editor-layout
python3 scripts/check-ui.py --devkit --release --phase-e --phase-c
python3 scripts/check-ui.py --devkit --release --selection-ui
python3 scripts/check-gnome.py --devkit --release --phase-d-atspi --selection
python3 scripts/check-gnome.py --devkit --release --phase-c-clipboard --phase-c-composed-input
python3 scripts/check-gnome.py --devkit --release --phase-c-clipboard --x11-clipboard
```

剪贴板备份跳过 X11 的 `SAVE_TARGETS`、`TARGETS`、`TIMESTAMP`、`MULTIPLE` 及插入/删除控制目标；仍保留真实数据格式（含 `UTF8_STRING`）并传播读取错误。`--x11-clipboard` 使用真实 XWayland GTK 剪贴板来源验证粘贴与多格式恢复。独立回归检查可运行 `GI_TYPELIB_PATH=/usr/lib64/mutter-18 LD_LIBRARY_PATH=/usr/lib64/mutter-18:/usr/lib64/gnome-shell gjs -m scripts/check-clipboard.js`。

`--selection` 用 `probes/xwayland-fallback` 的 Tk/Swing 夹具（需要 PySide6/Tk、JDK、xterm）检查 XWayland 兼容替换：确认、撤销、粘贴、词边界、密码、立即规则、应用排除、终端名单、不导出选区窗口的探测上限与替换期间插入的按键。`--selection-ui` 在私有会话中启动辅助功能总线和 XWayland，用不导出选区的 xterm 触发真实的“兼容替换不可用”结果，检查运行状态页的停用按钮和设置页排除选项。check-gnome 结束时还会停止在私有总线上被 D-Bus 激活、而非由脚本启动的 core。2026-10-22 在本机观察到：启用 XWayland 的 devkit 运行有时在共用准备步骤“隐藏概览”超时，或 Shell 输入帧数秒才到达，未启用 XWayland 的检查同时通过；遇到时重跑，不要放宽断言。

`--editor-layout` 检查规则/模板卡片填满工作区、独立滚动、规则取消及文本暂停保留草稿。XWayland 超时透传的故障测试为 `scripts/check-gnome.py --devkit --phase-d-atspi --ime --text-failopen`：暂停测试应用进程以阻塞真实 AT-SPI 响应，检查首次空格/Enter 恢复、后续原键直通和切换窗口后重新替换。NVIDIA 的独立测试桌面如遇 EGL 崩溃，可仅对测试命令设置 `__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json XWAYLAND_NO_GLAMOR=1 GALLIUM_DRIVER=llvmpipe`；无需更改主会话。

检查需要 `mutter-devkit`、`python3-gobject`、`WebKitWebDriver` 和 `tauri-driver`。后者可以安装到独立工具目录：

```bash
cargo install tauri-driver --version 2.1.0 --locked --root /你的/工具目录
export WAYSTROKE_TAURI_DRIVER=/你的/工具目录/bin/tauri-driver
```

测试使用私有 D-Bus、配置和独立 GNOME，并关闭 Devkit 与主桌面的剪贴板转发。常规入口不选择物理鼠标；真实设备接管测试需要单独安排，不能把虚拟输入证据当作实物热插拔通过。

## 设计与验证资料

- [产品需求与界面规格](product-design.md)
- [10 类、69 项动作目录](action-catalog.md)
- [实现计划与阶段验收记录](implementation-plan.md)
- [阶段 F 发布验证](../fixtures/phase-f/README.md)
- [技术验证记录](technical-validation.md)
- [界面设计稿](../design/README.md)

阶段 A–F 的当前结论以实施记录及各阶段证据为准；阶段 F 的实体接收器拔插验收由用户明确跳过，不标记为测试通过。

设计稿仅为界面参考，不代表实际系统行为：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory design
```

浏览 `http://127.0.0.1:8765`；窗口外的评审控件不属于正式软件。

## 图标与高刷新率

系统图标的矢量源为 `apps/desktop/src-tauri/icons/icon.svg`，圆角比例与应用内品牌图标一致。RPM 同时安装 scalable SVG 与 64×64 PNG；修改图标后用 `rsvg-convert apps/desktop/src-tauri/icons/icon.svg -o apps/desktop/src-tauri/icons/icon.png` 同步 Tauri 的 PNG。构建不会更新主系统已安装的图标。

桌面 WebView 启动时通过 WebKitGTK feature API 关闭 `PreferPageRenderingUpdatesNear60FPS`，让页面动画和 `requestAnimationFrame` 跟随显示器刷新率，并启用平滑滚动。实际帧率仍取决于合成器、显示器和渲染负载；没有设置固定 120/144 Hz 或空闲重绘循环。

本机 NVIDIA / WebKitGTK 2.54.1 仍有底层限制：120 Hz 显示器上 `drmWaitVBlank` 返回 `Operation not permitted`，WebKitGTK 回退到 60 Hz 定时器。关闭上述页面策略后的独立 WebView 实测仍约 59 FPS，因此此配置不能视为本机高刷新率已修复；需要 WebKitGTK 的同步实现或驱动侧修复。没有更改系统权限、驱动或全局渲染设置。

应用范围选择器位于 `apps/desktop/src/applications.js`。已安装应用由桌面端 `list_applications` 命令通过 GIO 读取，窗口标识由 GNOME 桥接提供；保存与匹配继续使用原有配置中的应用 ID，不更改配置格式。`--application-scope` 使用临时同名应用条目验证首次选择、按 ID 保存与重开、文本作用范围及手势标题条件，不安装应用或改动主桌面配置。原生测试的私有 D-Bus 激活文件指向被测构建，避免误用系统已安装的 core。

应用候选历史与隐藏项仅为界面偏好，保存在 WebView 的 `localStorage`（`waystroke.applicationCandidates`）中；完整已安装目录不加入候选。删除候选不移除配置中的应用名称映射，也不改写规则。应用范围专项检查覆盖目录不污染候选、四处删除控件、关闭重开后的隐藏状态与重新选取恢复。

原生输入事件可能只携带物理 `MOD4` 而不携带虚拟 `SUPER` 标志。文本与终端接入都将二者视为 Super 修饰键，避免把 `Super+Space` 拦截为替换确认。`--ime-shortcuts` 在私有 GNOME 会话中用两种输入源验证空白焦点、单行输入框、多行文本框的正反向输入源切换及普通空格；测试复制的扩展只记录空格事件的修饰位和上下文可用性，不记录输入文本。
