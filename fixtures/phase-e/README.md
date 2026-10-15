# 阶段 E 验收证据

配置迁移、持久备份与页面闭环。扩展和原生窗口检查全部使用私有 GNOME 50.5 / mutter-devkit；不部署主桌面、不选择物理鼠标，并关闭 Devkit 与宿主的剪贴板转发。

- `ui-native.json`：正式 Tauri/WebKitGTK 的文件检查与确认/取消、导入规则调用动作实际写文件、导入文本匹配、冲突模板/动作引用重映射和规则停用、同词文本保留、恢复/手动备份/删除、错误版本不覆盖、真实文件对话框取消及配置/备份/诊断保存、重启后的备份列表、真实登录入口创建/删除并从入口重启后台。包含八页、编排、变量/返回引用、真实选窗/执行、窗口操作、草稿断连与后台生命周期回归。
- `text-ui-native.json`：文本页正式匹配与撤销、真实 GTK 的文本状态/密码保护、停用和锁屏/解锁状态；原有阶段 D 的浏览器、IME、终端和 AT-SPI 功能证据仍在 `fixtures/phase-d`。
- `source.json`：运行命令、实际临时目录、源码/构建产物及测试副本哈希。`check-ui.py --phase-e` 只在私有扩展副本增加可控协议版本，实际 D-Bus 上报 99 后观察后台拒绝、原生页面显示实际错误和 0 项可用能力，再恢复为 1。配置、执行和文本路径都使用正式实现。
- `configuration-*.png`、`runtime-incompatible.png`：正式 WebKitGTK 窗口的真实空态、摘要、确认、错误和版本不兼容状态。页面 CSS 和设计稿未改动。

重跑入口：

```sh
./scripts/build.sh
cargo test -p waystroke-model -p waystroke-core
npm run test:adapter --prefix apps/desktop
python3 scripts/check-core.py
python3 scripts/check-ui.py --devkit --phase-e --phase-c
python3 scripts/check-ui.py --devkit --phase-d
```

迁移的三项单元检查覆盖稳定 ID/内部引用、输入和返回字段与普通数据键、未知版本/动作/引用/递归、配置版本冲突、备份写入失败阻止覆盖、恢复前备份、5 份保留、磁盘导出/删除与重新打开仓库；另有一项验证初次设置门控、登录入口失败和配置失败的回滚。`check-core.py` 另外通过真实私有 D-Bus 验证扩展缺失时仍可导入/导出/备份/恢复。不是以页面截图代替这些效果检查。

备份只包含可迁移配置，迁移保留本机接入/授权状态，鼠标稳定身份作为偏好正常导出/恢复；诊断不导出配置正文、窗口标题、命令输出、剪贴板、按键流或文本替换正文。测试数据和截图均来自固定夹具。

安装包、系统级授权、安装升级卸载与发布验收继续属于原计划 F01–F03；本阶段没有运行这些主环境操作。

当前状态：E01–E03 已完成。新增向导检查实际启用已禁用扩展，并在卸载私有副本后重新安装正式资源，正确提示首次发现扩展需要重新登录。鼠标安装使用显式 pkexec 测试启动器验证取消和重试，实际安装程序将二进制、服务单元及 UID 配置写入临时前缀并检查内容/权限；没有调用主系统 systemctl 或管理员认证，不把暂存文件安装成功显示为服务已连接。真实 root 执行拒绝测试前缀。系统级部署和 RPM 的验收保留在 F 阶段。

`setup-authorization-canceled.png` / `setup-first-install.png` 展示真实向导错误和重新登录提示；`source.json` 区分首次加载源码和重新安装后的磁盘资源哈希。Rust 检查共 15 项（4 model、10 core、1 desktop 资源安装）。
