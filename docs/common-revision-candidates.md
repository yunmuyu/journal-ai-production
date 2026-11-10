# 共用终审修订候选入口

2026-11-03 用户确认：未终检候选须证明本图要求的重绘或换字已经执行；格式可打开、转成灰度或有可编辑对象均不能代替加工证据。已终检成图按当前稿件匹配关系复用，历史恢复不伪写为本版重新加工。

## 一条修订通路

保存反馈仍用原工作台。提交 `/revision-jobs/<figureId>`，带当前 `version`，得到分流记录 `id`。不启动 WorkBuddy、不领取生产任务。

协调者用现有 reviewer Bearer 身份提交：

```json
POST /review-triage/prepare-candidate
{"id":"<review-id>","productionRoute":{},"outputRoutes":[]}
```

单图可省略 outputRoutes。返回 `commonCandidate.task` 是路径/SHA，任务冻结原图、当前反馈内容及版本、原包/Word/清单、逐输出加工路线。保持原始批注不变。改变加工计划或重试失败加工，显式带 `newAttempt:true` 建立新尝试；旧目录不覆盖。已有同计划尝试可直接接续。

普通 JPG 继续用 `raster-job.mjs` 与其 self-check，免 PS。PDF 继续用 `journal_pdf` 公共工具生成；已有合格的新样张可直接封装，不需重复绘制。

```text
node workbench/pdf-candidate.mjs <task.json> <rendered-input.json> <existing-evidence.json>
```

此命令只封装隔离候选、复用 task_quality 预检/后检并验证加工证据，不发布或验收。重复相同请求检查原证据后返回同一候选；失败目录保留，重试用新尝试。

rendered-input：

```json
{
  "outputs":[{"number":"1","path":"<rendered.pdf>","sha256":"<sha256>"}],
  "processingEvidence":[{"number":"1","report":{"path":"<report.json>","sha256":"<sha256>"},"spec":{"path":"<figure.spec.json>","sha256":"<sha256>"},"sourceRoot":"<source-root>"}],
  "summary":"本次实际修订及仍待确认事项"
}
```

existing-evidence 必须来自真实核对，不能由封装器编造：`producer`、`qualityRoute`（diagram/circuit/source-preserving-chart）、`history`、`frozen_manifest`、`author_roots`、`delivery_targets`（图号→只读核对的交付目标）、`runtime.python`/`runtime.font_profile`（均为路径/SHA）、`allowed_changes`、`immutable_content`、`failure_policy`。结构沿用 task_quality。主 source 须为核对过的可预览单页 PDF/PNG/JPG；原 PPTX/Word/压缩包仍绑定在 source_inputs 和路线来源中。

最终统一登记：

```json
POST /review-triage/import-candidate
{"id":"<review-id>","candidate": {"attempt":1,"outputs":[],"contract":{},"submission":{},"outputBindings":{},"processingEvidence":[]}}
```

PDF 的 candidate 直接读取 pdf-candidate.mjs 返回的文件。JPG 为 `{"attempt":1,"result":<raster-job带selfCheck的result>}`。共同检查原稿/当前批注/源哈希，成功后只进入待终检，保留旧输出，不改 acceptance.json 或 feedback.json。检查完成到发布之间再次核对基线。过期尝试、旧 PDF、缺证据、错图号和错来源均不放行。

旧作者清单只用于恢复已登记历史候选，新的修订必须走上面的统一入口。旧 WorkBuddy/Codex 执行器不会因准备候选而启用。

## 加工要求与真实证据

`productionRoute.processing` 至少有 `operation`、具体 `basis`。换字另有唯一 `targetTextIds`，对应本次需要处理的完整文字集合，不能仅写“字体已改”。

| operation | 公共工具证据 |
| --- | --- |
| preserve | 明确无需换字的 JPG；原有 raster 计划冻结、实际重放和自动质量检查继续执行 |
| rebuild | 公共图布局的节点、可编辑文字、当前引擎/说明/源件/候选哈希绑定 |
| vector-reletter | 原生 PDF 场景换字登记与原路径保留证据，逐项匹配目标文字 |
| raster-reletter | 场景中的每个遮字区域、已核对非数据背景、原文与目标文字一一对应；区域外像素不变 |
| chart-redraw | 现有 SVG/位图统计图公共加工：保留原数据路径或像素，重新排刻度、单位和图例；不从图片猜测数据重画曲线 |

PDF还核对正式字体、实际可提取文字、灰度、页边及独立 task_quality。逐输出使用各自来源和加工要求，不能用第一张图报告覆盖其他图。源转曲字、复杂混合对象、VSDX等仍按工具已实现的证据能力处理；不能用简单重绘报告冒充未实现的换字。

场景位图入口现在确实传递遮字参数；未登记遮罩、漏目标文字及未核对安全区域均报错。通用 PDF 导出默认0.25 pt保护留白，在布局外增大画布，避免页边标签的留白被旧画布裁掉；实际 PDF 四边未达到请求留白（1200dpi、容差0.065pt）或导出超过栏宽会阻断。该修补不缩放图形、字号或改变分支。

## 恢复与验证范围

共用修订保留 task、报告、说明、候选、质量契约和发布回执。重复回传与重启按已发布证据恢复，不因后来引擎升级重写历史。恢复仍检查反馈、Word、来源、候选、预览和封存文件，已验收版本不能被另一候选覆盖。

测试覆盖真实 PDF 渲染→公共封装 CLI→HTTP 回传→重复提交→重启恢复，以及真实免 PS JPG 重放回传。机械证据不是来源语义的自动证明：位图原文/遮罩语义、逻辑连接、单位含义与最终视觉仍由用户终审，不能将 pending 改成已验收。
