# WayStroke

面向 Fedora 44、GNOME Shell/Mutter 50.5 Wayland 的鼠标手势与文本替换应用。

当前完成产品设计和核心桌面接入验证，正式工程尚未实现。项目内的 HTML 是界面设计稿，probes 是技术验证工具，两者都不是已经完成的应用。

开发依据：

- [产品需求与界面规格](docs/product-design.md)
- [声明式动作目录：10 类、69 项](docs/action-catalog.md)
- [技术验证与原始证据说明](docs/technical-validation.md)
- [完整开发计划与验收清单](docs/implementation-plan.md)
- [界面设计稿预览](design/README.md)

采用 Tauri 2/TypeScript 界面、Rust 普通用户后台、GJS GNOME 扩展与独立特权鼠标服务。完整开发计划已落地，覆盖逐页真实功能、69 项动作、进程接口、任务依赖和发布验收。UI 必须按 HTML 一比一复刻；只有界面或固定样本反馈不算交付。下一阶段按计划 A01–A04 建立工程、正式数据模型、真实配置读写和原生 Wayland 桌面壳。

设计稿预览：

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory design
```

访问 `http://127.0.0.1:8765`。桌面窗口外的评审控件不属于正式应用。
