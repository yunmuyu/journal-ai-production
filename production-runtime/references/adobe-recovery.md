# Illustrator 脚本故障：低成本接手指南

适用于 Illustrator 窗口和 COM 对象仍可访问，但脚本调用异常的情况。诊断和恢复均以当前 JOB 为边界；不把一个 JOB 的 Adobe 故障扩大为停止其他格式任务。

## 已确认的案例事实

2026-09-23，Illustrator UI 正常，COM 的 `Name`、`Version`、`Documents` 可读；但仅执行字面量的 `DoJavaScript` 和经 VBS SAFEARRAY 调用均返回 `-2147417851`。切换前台没有作用。唯一打开的文档确认 `Saved=true` 且 `PageItems=0`。正常调用 `Quit`（没有 kill 进程）后重新通过 COM 启动，纯 JavaScript 探针恢复。随后在隔离副本中，对同一路径 AI 执行 trim 完整通过（15 个文本、0 个机械问题），脚本接口仍健康。

这组证据支持“该次 Illustrator 进程内脚本状态异常，正常重启后恢复”。触发异常的原因未知；同一路径 trim 成功不能证明原始故障由保存同路径导致。

## 短决策表

| 观察结果 | 下一步 |
| --- | --- |
| 诊断为 `healthy` | 不重启。只继续当前 JOB，并按其阶段日志检查结果。 |
| `script_fault` | 检查是否有 JOB livelease；有则停止对此 Adobe 实例的操作。确认无 livelease 后，只允许一次受限的正常空文档重启，再做一次诊断验证。 |
| `com_unavailable` / `not_running` | 不做脚本调用或盲目拉起。保留报告；若 JOB 的占用状态也已核实停止，可用 `recover` 清理死 owner 后交由后续步骤处理。 |
| `probe_timeout` | 超时不是 Adobe 已空闲的证据。不要重启、删锁或再次探测；记录报告并停止该 JOB 的 Adobe 操作。 |
| `busy` | 诊断发现任务占用。不要并发诊断或恢复；等当前任务有明确结果后再处理。 |

诊断命令为只读、限时、不截屏、不抢焦点：

```text
node scripts/jfw.mjs doctor JOB
```

报告写入 `JOB/diagnostics/`。如果 JOB 存在 livelease，诊断应拒绝运行。每次故障最多做一次只读 probe；根据有证据的空闲状态重启后，最多再验证一次。不要循环重试。

## 受限重启

命令：

```text
node scripts/jfw.mjs doctor JOB --restart-empty
```

该入口只在没有打开文档，或所有文档都满足 `Saved=true` 且 `PageItems=0`，并确认没有 livelease 时才允许正常 `Quit` 后重启；执行前会再次核对 PID。任何有内容或未保存的文档都应导致拒绝。遇到拒绝时，停止并请用户保存、关闭文档后再运行。此入口不杀进程、不关闭有内容的文档，也不解除 JOB 锁。

## 恢复 JOB 占用

只有在确认旧任务已停止、相关 Adobe 操作空闲后，才运行：

```text
node scripts/jfw.mjs recover JOB --verified-idle
```

`recover` 只解除已退出 owner 的锁，并把遗留的 `rendering` 状态标记为 `interrupted`；它不修复 Illustrator 引擎，也不会删除源文件。观察超时本身不构成 `verified-idle` 证据。若发现 livelease、仍存活的任务 PID、格式异常的锁，或租约属于另一个 JOB，立即停止，不要手工删锁。

## 接手时的最短清单

1. 先读本说明、[运行说明](../运行说明.md)以及当前 JOB 的 `events.jsonl`、状态文件和 `diagnostics/` 报告；不要重新跑整批任务。
2. 确认 Adobe 文档是否有未保存内容、`PageItems` 是否为空，以及是否存在 JOB livelease。不要只凭 UI 可见或超时推断空闲。
3. 最多执行一次 `doctor`。仅当结果和进程/文档证据一致、没有 livelease 时，才考虑一次受限重启；之后最多做一次健康验证。
4. 若无法确认空闲，或恢复后仍异常，停止这个 JOB 的 Adobe 阶段，保留诊断材料。其他不依赖该实例的任务可以继续。
5. 向用户报告观察到的状态和报告路径，不声称未经观察的步骤通过。

禁止用桌面截图探测、盲目 SendKeys、强杀 Adobe、盲删锁或伪造通过证据。机械检查通过只说明该检查通过；不等于完成视觉复核或 `visual pass`。视觉验收仍须按运行说明查看真实 PDF/图像并记录证据。

## 已验证范围与未解决问题（2026-09-23）

- 调用桥在执行真实脚本前先运行字面量健康探针；探针失败不会继续写图。
- 即使 result.json 已写出，COM 在返回完成前异常也保留 Adobe 租约；不能以文件存在推断调用结束。
- 49 项自动测试通过。真实未保存测试文档导致 `restart_refused`，文档仍在；只关闭了这个自建测试文档。
- 两张齐共新历史图实际 draw、trim、PDF 审计成功，宽79.508/79.476mm，机械问题0。仍是 needs_review 测试样本，不据此认定出版质量通过。
- 12:57 的受限空文档重启成功，PID 37080 → 16544，报告 healthy/restarted=true。证据：工作区 `work/adobe-recovery/restart-final.json`，`tests-final.txt`，JOB diagnostics。

### 启动时“无法在文件内设置位置。”

这是另一类原生启动故障。出现时 `doctor` 返回 `startup_dialog`（只读取 Illustrator 自有对话框的标题/按钮，不截取桌面），或 `startup_exited`、`restart_pending`。**保留状态未确认租约，不循环启动。** 排查旧 worker 是否仍活着；一次 tool 超时可能只结束父命令，不能据此认定 cscript 已退出。

本次磁盘空间、设置数据库完整性检查未发现对应损坏。只重置主首选项仍失败，已恢复原文件。1096 个经文件头确认的 Adobe FontList 缓存已移入工作区 `work/adobe-recovery/font-cache-quarantine`，完整设置备份在 `settings-backup-20260923`；字体文件、复合字体、用户脚本没有删除。隔离缓存后最初仍失败，随后启动成功，**不能将缓存判为已证实根因**。

若再发生：保存报告，停止该实例上的自动化，让用户手动启动作为兜底；其他非 Adobe 工作继续。恢复旧缓存仅在 Illustrator 完全退出后，按备份逐项还原，不覆盖新设置。不自动重置全部偏好，不通过强杀或反复点启动碰运气。

工具调用超时应长于被调用程序的内部上限；长操作保存日志，等待工具完成，不使用 1 秒外层 timeout 截断父进程。
