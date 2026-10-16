# 阶段 F 验收证据

状态：软件实现、隔离 RPM 生命周期和 Devkit 验收已通过；F02 接管期间的真实鼠标拔出/重插及恢复仍缺少证据，F03 最终发布门槛随之保持未完成。阶段 B 曾由用户选择跳过实机重插，此处不把旧跳过改写为本阶段通过。

| 结果 | 证明范围 |
| --- | --- |
| `devkit-desktop-final.json` / `devkit-displays.json` | release core 与正式扩展，mutter-devkit 双屏（1.0 / 1.25 缩放），桌面/真正 GTK 瞬态窗口/未聚焦起点，窗口与工作区枚举，反馈居中，锁屏/解锁，扩展重启旧句柄失效及队列取消，core SIGTERM 正常退出、重开配置保留。 |
| `native-ui-release.json`、八页 PNG 与 `composer.png` | 最终 release 原生 WebKitGTK；向导、配置/备份和真实文件、编排/保存/变量，关闭后台继续、重开和真正退出。截图等待当前帧绘制；不使用 Chromium。 |
| `text-lifecycle-final.json` | 无诊断注入的正式文本源码；确认/立即/撤销/自身输入/密码/排除，旧焦点请求取消，同焦点输入排队时保存配置后 `abcxyz` 完整送达；core/IBus 断连与恢复、锁屏/解锁。 |
| `terminal-final.json` / `atspi-final.json` | 共用队列改变后的实际 Ptyxis/VTE 与 XWayland GTK 回归：确认与重放、立即、密码策略、生成输入抑制、焦点取消等对应分支。raw/TUI 仍只声明提交字节，不声称文档级兼容。 |
| `rpm-lifecycle-final.json` | 实际 Fedora44 rootless Podman + systemd，DNF 安装、RPM 1→2 升级与卸载，安装不启动/启用服务或写授权，真正会话激活，UID/0600 授权配置，probe 停止，配置/备份保留及卸载清理。正式 polkit 策略解析成功，非活动会话拒绝授权且无副作用。 |
| `inputd-disconnect.json` | 同一容器中真正 GNOME50.5、release core 与 root inputd；停止实际服务后运行任务取消、排队任务未开始，实际按住的 Shift 被释放；恢复服务后重新连接。无物理抓取。 |
| `installed-desktop.json` / `installed-desktop.png` | RPM 文件在只读挂载命名空间按正式 `/usr` 路径运行，Devkit 实际渲染设置与向导；无开发库路径，真实会话激活、关闭后台继续、重开复用与正常退出通过。主机 `/usr` 不变，采用私有 `/dev`，没有宿主设备绑定。 |
| `rpm-payload.json` | RPM 内 3 个可执行文件、7 个扩展资源、2 个原生资源的摘要与受测构建产物逐项一致。 |

`text-regression-before.json` 是修复前的失败历史，不能当作当前结果。`devkit-lifecycle.json`、`rpm-lifecycle.json` 是中间通过结果；当前结论使用上述最终结果。`verification.json` 记录当前源码、产物摘要和尚未通过的范围。

本阶段修复：无鼠标租期时扩展断连没有取消动作；inputd EOF 未清除待完成轨迹及队列；core 缺少 SIGTERM 清理；保存回调在导航后覆盖新页面；混合缩放文字尺寸首次布局后变化未重新居中；文本队列等待未受服务的帧，以及配置更新清空同焦点排队的普通输入。配置改变继续取消旧编辑请求，焦点改变和锁屏继续丢弃失效上下文。

容器边界：`/dev/uinput` 明确用 `/dev/null` 链接作为空闲启动夹具，未证明真实 uinput/抓取。polkitd 以其实际 UID 直接运行，绕过 rootless 容器不能提供的 systemd 命名空间沙箱；正式主机单元未改变。inputd 联测容器无宿主显示通道，采用独立 headless Shell；常规扩展、文本与 UI 验证使用 Devkit。容器软件图形沙箱/线程池曾妨碍安装版界面核对，最终安装路径启动和截图改由只读 RPM 文件覆盖层 + Devkit 完成，未把失败截图改作通过。

重跑入口：

```sh
bash scripts/build-rpm.sh
bash scripts/check-installed-rpm.sh
python3 scripts/check-gnome.py --devkit --release --multi-monitor --phase-f --phase-c-window
python3 scripts/check-ui.py --devkit --release --phase-e --phase-c
python3 scripts/check-gnome.py --devkit --release --phase-d-text --focus-race --lifecycle
python3 scripts/check-gnome.py --devkit --release --phase-d-terminal
python3 scripts/check-gnome.py --devkit --release --phase-d-atspi --focus-race
cargo test -p waystroke-model -p waystroke-core -p waystroke-inputd
npm run test:adapter --prefix apps/desktop
```

`check-rpm.py` 只在具有 systemd PID1 的临时 Podman 容器执行，需要两个不同 release 的 RPM；`WAYSTROKE_RPM_RELEASE=2 bash scripts/build-rpm.sh --skip-build` 产生第二个包。`check-container-inputd.py` 同样限定容器，只控制容器的固定 inputd 单元，不操作宿主服务或输入设备。

剩余真实设备验收需管理员安装本次 RPM，经向导授权鼠标服务，在实际加载匹配版本的扩展/core 中明确选择测试鼠标。需要记录接管期间拔出后的释放/状态、重插后的稳定身份重新接入，以及普通点击和一条安全手势。空闲容器服务不能替代该结果。


2026-10-16 更新：主机会话已实际加载正式扩展，管理员授权已完成。重启暴露的已授权服务未启用问题已通过 release `0.1.0-2.fc44` 修正并安装。`rpm-boot-recovery.json` 证明真实 systemd 容器重启恢复已授权 idle 服务、升级迁移及卸载清理；`rpm-boot-fix-payload.json` 对应新包与不变的程序/扩展资源摘要。主会话 G304 实际接管与专用窗口手势最大化已成功；`hotplug-live.json` 是仍在进行的原始记录，暂未观察到接收器拔出/重插，不能将该文件视为完整热插拔通过。最终状态见 `verification.json`。


最终状态（2026-10-16）：用户明确要求跳过接收器拔插测试，F 在此豁免下完成。`verification.json` 保留 `physicalReplugPerformed=false` 与具体用户指令，不把该项标为通过。`hotplug-live.json` 仅证明实际鼠标手势匹配与专用窗口动作成功；`hotplug-client-final.json` 记录窗口确已最大化且右键未保持。临时规则已移除，原完整配置及开启的手势偏好已恢复；专用测试窗口、观察器和容器均已停止。上述历史“等待拔插”不再是当前待办。
