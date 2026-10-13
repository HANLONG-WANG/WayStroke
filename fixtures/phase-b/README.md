阶段 B 验证证据（已完成本轮；重插按用户要求跳过）

- input-preparation.json：已安装服务、真实 G304 准备和释放；未接管、未注入。
- gnome-ready-barrier.json：主会话 Ready 同步标记；73 ms 不代表松键延迟。
- desktop-results.json：隔离 GNOME 的真实基本执行器、窗口身份和队列取消。
- ui-results.json / dialog-real-execution.png：正式扩展与原生 UI 的识别、窗口选择、执行详情及生命周期。

以上准备/隔离结果不替代实机检查；下方 live-* 文件提供物理输入证据。重插由用户明确选择跳过，未验证。

- live-performance-retest.json：完整 21 次实机事件（20 条有效轨迹、1 次短点击），5 条匹配并真实执行回车/最大化/计算器；用户确认流畅但难触发，不能宣称识别质量验收通过。
- trail-live-name.json / trail-live-name.png：隔离 GNOME 实时标签、批量增量预览及清理，3 秒 181 帧、CPU 0.28 s；不是物理输入到名称显示的端到端证据。

- live-name.json：新版实时名称实机动作记录，用户确认名称变化与流畅性正常。
- desktop-cancel-feedback.json：隔离 GNOME 的 Esc/停留取消标签清理，以及双屏执行提示下方居中；不替代实体输入和锁屏重插检查。

- desktop-native-lock.json：独立 GNOME 原生遮罩状态、实际运行/排队动作取消及恢复。
- live-lock.json：用户主会话锁屏行为正常；扩展停用时释放输入，解锁后实际恢复执行。重插由用户明确选择跳过，未验证。

- live-load.json：实际 30 秒单核负载范围内的两次 A→B 手势及 A 的成功动作、绑定/识别/排队时序，用户确认正常。
- trail-quiet-start.json：最小长度前初始标签隐藏，匹配名称正常，结束清除。

最终逐项核对见 docs/implementation-plan.md 的“阶段 B 收尾结论”。软件整体尚未完成，C–F 继续按计划实施；重插始终记为未验证。
