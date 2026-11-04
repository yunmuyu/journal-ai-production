# 公共回执、失败分类与产量统计

PDF继续走 `production-runner.mjs`，JPG继续走 `raster-batch.mjs`。两条入口共用 `production-observability.mjs`；没有新增执行器、调度服务或自动重试循环。Adobe不接入此并发路径。

## 一张图什么时候计为回传

公共核验器读取当前工作台，核对图件身份、完整输出集和SHA，实际下载输出并比较SHA、读取预览，再确认工作台版本及输出未变化。通过后写 `production-delivery` 回执，保留批次原包SHA、文章ID、图件ID、作者、编辑、图号、输出SHA、普通/修订类型及首次核验成功时间。

回执不是用户终审通过标记，也不是当前工作台状态副本。后续修订或撤回不会抹掉历史交付记录；当前可用版本仍以工作台为准。

PDF/JPG配置可显式指定相同 `receiptRoot`。默认PDF使用 `<workbenchRoot>/production-receipts`；JPG有workbenchRoot时相同，否则兼容使用 `<attemptDir>/production-receipts`。旧JPG配置仍能运行；要集中统计，应由协调者给两条路线配置共同的回执目录。凭证不写入回执。

同输出重复核验沿用首次回执，不改变首次时间。接入前已完成、没有公共回执的历史候选重新核验时标记 `historical`，不冒充本小时新增。JPG发布前保存 `delivery-pending.json`，发布成功但预览失败时保留待核验结果，后续prepare返回已有成图后可继续核验，不重新发布，也不将服务端已ready的任务改成failed。

## 查询指定窗口

```text
node workbench/production-observability.mjs report-window.json
```

输入示例（配置保存在仓库外）：

```json
{
  "receiptRoots": ["<共同回执目录>"],
  "from": "2026-11-03T12:00:00+08:00",
  "to": "2026-11-03T13:00:00+08:00"
}
```

窗口左闭右开，时间必须带时区。只读扫描指定目录中的回执JSON，不递归猜测整个磁盘。不存在的目录、损坏文件及内容冲突的重复回执会报错，不悄悄生成错误的零产量。重复目录、相同回执副本只计一次。

- `deliveredFigures`：工作台来源、批次、文章及图件身份去重的图件数。
- `deliveredOutputs`：同一图件下按输出图号及内容SHA去重的文件版本数。修订出新SHA会增加此项，重复原SHA不会。
- `deliveryEvents`：完整输出集的不同交付回执数；一图多个分图仍属于一个交付集合。
- `revisionDeliveries`：上述回执中经修订路线交付的数量。
- `figuresPerHour` / `outputsPerHour`：上述数量除以用户指定窗口小时数，不默认把几秒样本外推成整批吞吐量。
- `historicalReceipts`：扫描目录中排除在新增产量外的历史补核验回执数，与窗口内产量分开。
- `deliveries`：可用于“批次—作者—图号已回传”的结构化明细。批次身份为原包SHA，展示名称由现有批次目录映射；不猜月份或批次名。

统计的时间是候选文件和预览首次完整核验成功的时间；网络故障期间实际提交时间可能更早，不能将此指标称为服务端提交时间。批量报告新增 `returnedFigures` 和 `failureCounts`；原有 `returnedOutputs` 仅计本次创建的非历史成功回执。单图失败不阻塞同批其他任务。

## 失败分类

公共 `failure` 对象包含 `code`、`stage`、`action`、`message`、`automaticRetry:false`。它提供机器可读分类和处理方向，不授权自动改图、改来源或无限重试。

| code | 处理方向 |
| --- | --- |
| stale_version | 重新读取当前版本并核对方案 |
| source_changed | 重新核对来源和证据 |
| claim_blocked | 核对占用者，不夺锁 |
| visibility_unavailable / transport_failure | 优先核对已有候选和服务状态 |
| visible_output_conflict | 核对工作台当前身份和输出 |
| plan_rejected | 核对制作方案 |
| render_failed | 查看工具日志及具体诊断 |
| quality_gate_failed | 查看质量报告，不放宽标准 |
| publication_failed | 核对服务端任务状态 |
| unknown | 原样保留错误，进一步诊断 |

这些是有限的错误类别与执行阶段，不冒充已经判明全部根因。PDF未获显式重试时直接返回原失败状态和 `retryBlocked:true`，保留首个错误和失败时间；批量与JPG报告保留失败信息。现有显式重试控制保持不变。

## 验证边界

回归覆盖真实PDF新图/修订、真实JPG批处理、发布后预览故障恢复、重复调用、来源版本冲突、同图并发核验、历史回执排除、时间窗口和统计CLI。测试使用临时工作台、随机端口和合成图，不能代替真实批次产能测量。
