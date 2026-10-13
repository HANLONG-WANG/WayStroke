# WayStroke

面向 Fedora 44、GNOME Shell/Mutter 50.5 Wayland 的鼠标手势与文本替换应用。

正式工程已实现阶段 A 的原生桌面窗口、配置编辑与持久化后台。当前可创建和保存规则、自由手势模板、可复用动作及文本规则；全局鼠标接入、动作执行和文本自动替换由后续阶段完成。HTML 保留为视觉基线，probes 仅用于技术验证。

开发依据：

- [产品需求与界面规格](docs/product-design.md)
- [声明式动作目录：10 类、69 项](docs/action-catalog.md)
- [技术验证与原始证据说明](docs/technical-validation.md)
- [完整开发计划与验收清单](docs/implementation-plan.md)
- [界面设计稿预览](design/README.md)

采用 Tauri 2/TypeScript 界面、Rust 普通用户后台、GJS GNOME 扩展与独立特权鼠标服务。完整开发计划已落地，覆盖逐页真实功能、69 项动作、进程接口、任务依赖和发布验收。UI 必须按 HTML 一比一复刻；只有界面或固定样本反馈不算交付。阶段 A 的代码位于 `apps/desktop`、`crates/model`、`crates/protocol` 和 `crates/core`；接下来按阶段 B 接入真实鼠标手势。

设计稿预览：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory design
```

访问 `http://127.0.0.1:8765`。桌面窗口外的评审控件不属于正式应用。

开发运行（已安装本机开发依赖）：

```sh
npm ci --prefix apps/desktop
./scripts/build.sh
./target/debug/waystroke
```

窗口会启动同目录的 `waystroke-core`。关闭窗口后后台继续运行；运行状态页的“退出 WayStroke”同时退出窗口与后台。开发时使用 `npm run dev --prefix apps/desktop`，该命令先生成类型并构建后台。

配置存于 `${XDG_CONFIG_HOME:-$HOME/.config}/waystroke/config.json`，首次为空配置。保存由后台校验并原子写入；浏览器 localStorage 不参与正式配置。

必要检查：

```sh
cargo test -p waystroke-model -p waystroke-core
npm run test:adapter --prefix apps/desktop
python3 scripts/check-core.py
python3 scripts/check-ui.py
```

原生 UI 检查在独立 GNOME、私有 D-Bus 和临时 XDG 目录中运行，不接管真实鼠标。需要 `python3-gobject`、GNOME Shell、`WebKitWebDriver` 和 `tauri-driver`；后者可用 `cargo install tauri-driver --version 2.1.0 --locked` 安装，也可通过 `WAYSTROKE_TAURI_DRIVER` 指定路径。检查会输出临时截图与结果目录。视觉基线和阶段 A 证据见 [fixtures/ui-baseline](fixtures/ui-baseline/README.md)。
