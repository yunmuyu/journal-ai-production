# 接入现有对话／Agent，而不是替换正式生产入口

这是独立的只读前置筛选候选 v0.2.0，不是已合并到 GitHub 的发行版，也不替换直接 PDF 后端。仓库基线为 `ced82c85cb1a8490c52750e772a9415e6ac705f6`；读取了 AGENTS.md、README.md、RELEASE.json、prepare-decisions.mjs 和正式 editorial-profile。

## 两阶段协议

1. `python -m journal_preflight probe input-manifest.json --out <新证据目录>`：一次读文件，提取 Word 图题/媒体关联、PDF 实际内容对象、SVG/draw.io 结构，产生匹配候选。不会执行图片脚本、访问外部链接、OCR、扫描字体或修改原稿。自动候选从不标成已确认匹配。
2. 现有 Agent 看证据与原稿，填 `agent-review/2`：确认源配对、交付范围、保护策略、处理路线、内容疑点；由 `python -m journal_preflight route probe.json review.json --manifest input-manifest.json --out <新候选.json>` 验证来源快照并生成结构化路由。

`scan()`、`apply_review()` 是可直接调用的 Python 接口。未来独立上传入口可复用相同输入/输出；本版没有付费模型调用、后台任务、上传网站或通用识图服务。

## 保留的硬约束

Word 当前身份及完整图号、交付范围、源版本配对、同图已确认修改、已确认并锁定的栏宽仍然是硬约束。初步源探查可并行，但正式制作不能绕过它们。来源页数、附件文件数、Word主图数、内部面板数、导出PDF数量分别记录。未明确用途的孤立源可做技术探查，不能自动进入作者交付。

照片、地图、热图不会按类型一律D级；先看可保护/可组版的能力。级别是Agent建议，能力状态与问题逐项记录。`source-color` 需要既有授权与哈希证据：科学保彩需求不等于批准。筛选报告可以展示原图，但这不放行彩色生产稿。

栏宽建议是候选，不因Word图宽超过80mm就自动锁双栏。默认8pt先测实际容量；6～8pt的整图适配继承现行规则，不按旧序列导出8/7/6三套。不把原图CSS字体诊断或屏幕缩放当最终真实字体测量。

## 与既有 productionDecision 并存

正式前仍需 `find-prior-artwork.mjs` 和 `prepare-decisions.mjs` 对本机权威记录读取案例、同图用户纠正和原有已验收成果。本轮没有 record-root、production-results.json、evidence 或跨月作图目录，故标记为 **未读取**，不是“已检索无匹配”。

`python -m journal_preflight bridge legacy.json screening.json --out <新合并候选.json>` 仅在完全相同、显式给定的 figure ID 下添加 `aiProposal.preflightV2`。不覆盖 productionDecision、旧建议、caseRetrieval、userCorrectionContext、验收历史或锁定栏宽；未匹配的ID原样保留。现有ID映射必须由接入Agent显式提供，不能按作者名/文件名猜。

桥接输出仍然是候选。后续正式消费端必须以本机最新用户纠正和原有栏宽决定再校验，不能拿本轮建议盖过已确认值。`ready_for_publication` 固定 false；没有 `.ai` 不阻塞直接PDF路线，但字体、颜色、数据与实际PDF检查不能删。

## 边界

本版已实现源探查、draw.io结构提取、媒体关联、匹配候选、快照失效、路由与只增不改的兼容桥。**没有实现任意图的自动拓扑语义判定、任意截图自动正确识字、复杂框图重排、自动清字安全区认定或生产PDF渲染。** 这些不得由筛选等级冒充通过。

SVG 的回退文字图片不能使整图被误判为纯位图；有原生caption的PDF也不能被误判为可编辑统计图。原生draw.io中的vertex/edge对象计数包含标签、图例等，不能直接宣传为语义节点/关系数。

测试使用合成素材；真实作者材料仅在结果包，不能上传公开代码仓库。源码包不含字体、缓存、作者原图、Word、机器路径配置或完整正文。

实际路由CLI必须提供当前输入清单重新核对原文件哈希；仅旧probe与旧review相互一致不算当前源核实。Python API不传manifest时单列live_source_snapshot待核，不能正式下发。桥接保留同一建议的历史，冲突栏宽另加门禁，不改原确认值。

候选现已提交分支 `task/preflight-v2-agent-20261015`，提交 `14994c36f2bbccd528bc17f9c374a0bbeda6153e`，草稿PR #4；没有合并或部署。正式入口仍按原授权规则运行。
