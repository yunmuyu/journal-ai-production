# 公共生产执行入口

公共回执、失败分类和指定时间窗口产量统计见 [production-observability.md](production-observability.md)。PDF和JPG共用可见性核验；配置共同的 `receiptRoot` 可集中统计，未配置时沿用各入口默认目录。

`workbench/production-runner.mjs` 承接已核对的 PDF 制作方案，完成加工、封装、检查、普通/修订分流和工作台可见性核验。现有 JPG 仍使用 `raster-batch.mjs`；本轮没有新增引擎、调度服务或作者专用生产脚本，也没有将两种接口冒称全部合并。

## 调用

```text
node workbench/production-runner.mjs machine-config.json plan.json
node workbench/production-runner.mjs machine-config.json batch.json
```

批量文件为 `{ "concurrency": 3, "plans": [...] }`。不同图件独立领取、目录隔离、完成即提交；同图重复领取被锁拦截。检查封装也在独立子进程运行。任务失败不阻断其他任务。

机器配置由主协调者维护：`origin`、`workbenchRoot`、`credentialsFile`、`python`、`fontProfile`，以及必需的 `runtimeLock: {python: {path,sha256}, fontProfile: {path,sha256}, engineSignature}`。签名必须取自已验证版本，禁止启动时自动接受任意新签名。入口在加工前及登记前核对实际模块位置、引擎签名、Python与字体配置SHA。凭证文件沿用工作台配置，不向Agent发凭证；不继承代理随意设置的旧PYTHONPATH。

方案必需字段：

- `figureId`、`baseVersion`：工作台真实图件ID及reviewVersion。
- `outputRoutes`：完整逐输出图号与已经核对的productionRoute，必须明确processing.operation及basis。
- `history`：既有成图核对证据引用、conclusion、reusable。证据文件为checked/conclusion/reusable/observation四字段，不能凭空填写已核对。
- `qualityRoute`、`allowedChanges`、`immutableContent`、`articleEvidence`：实际制作判断。
- qualityRoute严格只接受diagram、circuit、source-preserving-chart、raster；电路选circuit，不能自造source-preserving-circuit。显式state=held/blocked/suspended或doNotRunUntilBlockerResolved=true禁止派发。
- `render`：逐输出的number、spec路径及SHA、sourceRoot；或者 `rendered`：已生成的outputs及processingEvidence。优先复用现有合格候选。

Agent不再提供contract、submission、frozen清单、交付路径或普通/修订HTTP请求。工作台仍是唯一状态权威，用户验收不会由此工具完成。

渲染前检查来源在指定根目录内、SHA一致、输出与来源隔离；冻结本次spec副本后执行。实际PDF、报告和固定引擎签名必须一致，实测宽度只能收紧方案栏宽，不能自动扩大。普通文字框不得用container标记绕过测字留白；容器须含实际子框或源资产。已存在候选且没有批注/重做授权时拒绝新覆盖。

## 接续与失败

- 状态保存在工作台 `production-runs/<figureId>/<方案SHA>/state.json`。相同请求已回传时复核输出SHA、HTTP文件字节及预览，不重复出图或登记。
- 提交前即保存候选引用。网络中断后先读真实工作台；必要时只重放同一候选或恢复已持久化登记，不重新生成。用户批注、验收或版本变化仍由现有服务端门禁拦截。
- 失败保留原日志与阶段；默认不自动反复重试。协调者诊断后可显式设置 `retryFailed: true`，错误历史仍保留。共享能力错误应集中挂起同类任务，不能换Agent继续碰撞。
- 旧普通PDF任务可通过机器配置 `preparedTasks[figureId]={path,sha256}` 接续。只接受同来源、同输出SHA和同加工操作的旧任务。若差别只是最终PDF实际裁边宽度，新接口 `retry-imported-pdf` 建立新attempt，不覆写原attempt；宽度不能增加，完整来源重新校验。服务端模块变更须重启后生效。
- 若未手工指定preparedTasks，入口从服务端当前running任务及工作台标准目录查找唯一的imported-pdf任务，沿用同一套来源/输出/加工检查。显式retryFailed允许将未生成candidate.json的封装中断通过同一retry接口接到新attempt，原目录保留；不重做已有PDF，不接受多任务歧义或已回传覆盖。
- JPG保留入口也在开工前核验processing，不能把需要换字的图按PNG后缀走灰度保留。

## 并发和产量

PDF完整链路现已验证6路渲染进程重叠、封装并行及逐项回传；实际生产额度为6，任务少于额度时只启动就绪任务。JPG接受正整数并发配置，当前真实回归覆盖2张同时处理；没有3/4路人为上限。Adobe特殊处理仍串行，不接入此并发入口。普通PDF多输出证据传递未收口，登记共享挂起，不删除分图检查换取吞吐。

批量结果包含 `peakToolProcesses.render/check`（实际子进程重叠峰值）、逐工具耗时及 `returnedOutputs`（本次新增可见输出）。重复请求返回reused，不增加产量。每小时产量从真实returnedAt和图号/SHA去重计算，短样本不外推整批速度。

`returned` 只汇报为“候选已回传，待用户终审”，不能简称“做好/合格”。峰值统计是入口观测的工具命令重叠，不是操作系统全部子进程采样。统一回执和窗口统计见production-observability.md；共享故障与就绪队列见production-admission.md。路径/来源前置错误记preflight，不得归为render能力失败。runProductionBatch的onResult在每项完成时通知协调者，不必等整批结束。

恢复派发只给来源、图意、处理规则已确定且当前工具支持的任务。语义判断仍交Agent；转换、封装、检查和回传不再逐图派Agent操作。共用缺陷、缺少用户决定和未准备的来源都不是可运行任务。

## PDF图表派发前路线查找

统一入口可接收 `{ "concurrency": 2, "chartRequests": [{"figureId":"...", "requestedAt":"带时区ISO时间", "source":{"path":"...pdf","sha256":"..."}, "requirements":[...] }] }`。每项先读当前工作台；已有候选立即返回 `existing_candidate` 及当前文件哈希/预览是否核对，不生成新图。明确授权更正时才可设置 `allowExistingCandidate` 并提供更正方案。

随后检查当前固定引擎与PDF的原生文字、矢量对象、彩色路径和图片，列出原矢量换字、图表布局、面板组合三个公共入口及缺失绑定；`entryAvailable` 只说明组件存在，`sourceCompatible: unverified` 不是此源已通过适配。状态 `ready` 表示具备已绑定且哈希一致的制作方案，仍须执行完整渲染、质量和回传；`needs_bindings` 列出缺项；`unsupported` 只用于检查不到可用图形或文字对象。图例、面板、系列的语义归属仍需可验证的绑定，不凭相同颜色或一个解析器的失败作结论。

指定 `plan` 可提交完整方案；仅当稿件、原包、图件、输出号、来源、原文字/图表规格、加工要求、引擎和历史证据满足入口核验时保存方案。以后调用时显式提供相同 `requirements` 可检索；版本、来源、稿件、图号、规格或要求变化时不自动复用，多份不一致方案不猜。已有工作台候选优先，不重复制作。

`requestedAt` 应为用户提出图号的真实时间，准备、来源核对、渲染、检查和回传都计入180秒。超时返回 `deadline_exceeded` 和所在阶段；已开始提交的候选必须继续核验服务端状态，避免重复回传。旧 `plans` 调用缺少 `requestedAt` 时仅记录 `execution_only`，不能报告完整交付达标。入口阶段边界和工具子进程有截止时间，入口外的人工准备不能由程序强行中止，调用方必须传入真实起点。

每次查找的只读结果独立保存在图件 `production-runs/.../route-discovery/`；确认方案保存在 `chart-plans/`。纯解析、路线候选或离线渲染均不计工作台新增回传；只有通过统一入口和可见回执后才计入。
