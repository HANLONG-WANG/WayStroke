# README 截图

2026-10-16 在 Fedora 44 / GNOME 50.5 的独立 mutter-devkit 会话中，运行 `target/release/waystroke` 截取。窗口内容由原生 WebKitGTK 渲染，不是 HTML 设计稿或合成图片。

演示使用私有 D-Bus 和独立 XDG 配置。私有 core 的 `/run/waystroke` 被隔离，不能连接主机鼠标服务；Devkit 的剪贴板转发关闭。没有将演示规则写入日常配置。

| 图片 | 内容 | 完整窗口原图 |
| --- | --- | --- |
| [手势规则](gesture-rules.png) | 四条示例规则、应用范围和规则编辑器 | [原图](originals/gesture-rules.png) |
| [动作编排](action-workflow.png) | 窗口靠左、等待、通知三个已保存步骤 | [原图](originals/action-workflow.png) |
| [文本替换](text-expansion.png) | 示例关键词与正式匹配逻辑产生的展开结果 | [原图](originals/text-expansion.png) |

README 使用功能区裁切图，完整窗口原图保留实际接入状态。演示环境未接入实体鼠标，截图不能作为鼠标授权、物理手势或设备热插拔的验证证据。示例内容不随安装自动启用。
