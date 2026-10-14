# WayStroke

面向 Fedora 44、GNOME Shell/Mutter 50.5 Wayland 的鼠标手势与文本替换应用。

正式工程已完成阶段 A 的原生桌面窗口和配置后台、阶段 B 的真实鼠标手势闭环。阶段 C 的声明式执行器、69 项动作和原生编排已完成隔离/Devkit 验收；用户确认测试环境通过即验收通过，不要求主桌面验证。文本自动替换按阶段 D 实施。HTML 保留为视觉基线，probes 仅用于技术验证。

开发依据：

- [产品需求与界面规格](docs/product-design.md)
- [声明式动作目录：10 类、69 项](docs/action-catalog.md)
- [技术验证与原始证据说明](docs/technical-validation.md)
- [完整开发计划与验收清单](docs/implementation-plan.md)
- [界面设计稿预览](design/README.md)

采用 Tauri 2/TypeScript 界面、Rust 普通用户后台、GJS GNOME 扩展与独立特权鼠标服务。完整开发计划已落地，覆盖逐页真实功能、69 项动作、进程接口、任务依赖和发布验收。UI 必须按 HTML 一比一复刻；只有界面或固定样本反馈不算交付。阶段 A 的代码位于 `apps/desktop`、`crates/model`、`crates/protocol` 和 `crates/core`；阶段 B 已完成真实鼠标手势闭环，包含正式识别、录制互斥、实时名称及基本桌面执行器；重插验证由用户明确选择跳过。证据见 [fixtures/phase-b](fixtures/phase-b/README.md)，阶段 C 已完成，其余产品能力继续按 D–F 实施。

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

阶段 B 开发接入（GNOME 50.5，先构建）：

```sh
sudo bash scripts/install-dev-input.sh --user "$(id -un)"
bash scripts/install-dev-extension.sh
```

鼠标服务安装后保持空闲，不设置开机启动；安装脚本会重新开启已有扩展。当前 GNOME 50.5 会缓存已导入的 JavaScript，重新开启不能刷新已修改的代码；需要新桌面会话才会加载代码更新。仅重新启用原版本无需注销。启动桌面应用，在设置中选择实际鼠标，并完成接入向导后才会接管。`bash scripts/install-dev-extension.sh --uninstall` 移除开发扩展；鼠标服务卸载使用 `sudo bash scripts/install-dev-input.sh --uninstall`。

`python3 scripts/check-gnome.py` 使用隔离 GNOME、测试应用和临时配置，检查正式扩展以及 core 快捷键/启动/窗口执行器，不选择物理鼠标。不能用该结果替代 G304 的按键、屏障时序、拔插和锁屏实测。

阶段 C 开发回归可在可见 Devkit 独立桌面运行（不注销主桌面）：

```sh
python3 scripts/check-gnome.py --devkit --phase-c-clipboard --phase-c-composed-input
```

该入口使用私有总线和配置，并禁用 Devkit 与宿主的剪贴板转发。检查结束关闭自身测试进程；更新扩展只需重启测试 Shell。最终主桌面部署另行核实实际代码加载。
