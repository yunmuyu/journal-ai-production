# 内部生产决策经验

无用户案例页面；正式验收仍只读 production-results.json。

每轮预填先刷新实际文件证据，再运行 collaboration/scripts/prepare-decisions.mjs --record-root <权威记录目录> --evidence <案例manifest.json> --input <六项建议草稿.json> --index <内部索引.json> --output <新版本方案.json>。输出拒绝覆盖已有文件。索引按主图ID去重，内容变化归档旧索引。

本轮证据提取器及输入输出保存在项目受控 work/decision-review-pilot-20261012/cases；build_cases.py 支持 --record-root、--output、--sample-ids。提取器含本轮明确案例核对，后续只能依据记录增补，不能把作者专例推广为普适规律。

只匹配记录支持的加工路线与结构关系。源匹配不清、成品哈希不一致、无合适案例时返回无匹配；图种标签不得放行。检索引用保存于 aiProposal.caseRetrieval，不向浏览器发送案例集。

用户更改保存在同一正式图件的 productionDecision 中：原AI建议、修改列表、最终字段、确认动作及历史。修改后待Agent统一核查，未配置后台模型调用。Agent先读取这些修改，再更新下一版建议；不能把待核查说成已通过。

测试：node --test knowledge/decision-retrieval.test.mjs workbench/decision-store.test.mjs。
