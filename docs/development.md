# WayStroke 开发与构建

普通使用、安装及功能介绍见[项目首页](../README.md)。日常使用推荐安装 RPM，开发与常规回归优先使用独立 mutter-devkit 会话，避免开发扩展覆盖主桌面的正式版本。

当前目标环境为 Fedora 44、GNOME Shell / Mutter **50.5**、Wayland、x86_64；不保证其他版本可编译或运行。

## 构建准备

需要 Rust／Cargo、Node.js／npm、C 编译器和 `pkg-config`，以及 Tauri/WebKitGTK、Mutter 原生组件的开发依赖。相关开发包包括：

```bash
sudo dnf install webkit2gtk4.1-devel gtk3-devel librsvg2-devel \
  mutter-devel graphene-devel rpm-build glib2-devel
```

开发包必须与目标桌面的 ABI 匹配，尤其是 Mutter **50.5**。安装前核对软件源版本；不要为了补齐开发头文件意外升级到不支持的 GNOME 版本。`mutter-devkit` 是独立桌面测试工具，不能替代 `mutter-devel`。

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

```bash
python3 scripts/check-ui.py --devkit --release --phase-e --phase-c
python3 scripts/check-gnome.py --devkit --release --phase-c-clipboard --phase-c-composed-input
```

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
