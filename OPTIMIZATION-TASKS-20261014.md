# 非求解器优化任务清单 · 2026-10-14

基线：`ced82c85cb1a8490c52750e772a9415e6ac705f6`。分支：`task/batch-pipeline-20261014`。
清单先行提交：`bfa9ed0a276400daf8798b5ac8a27813e945729e`。

状态定义：候选实现完成不等于已上线或已通过真实作者终检。此次仅开发、离线测试和草稿 PR，不恢复正式生产，不安装、不合并。

| ID | 任务 | 本轮结果 | 未完成的接入/验收 |
| --- | --- | --- | --- |
| T0 | 核对基线与责任范围 | 已读现行契约、代码及交接；独立分支 | DevSpace 连接失败，未读取本机交接回执和实时台账 |
| T1 | 同篇特征档案 | 按 articleId 汇总已观察的软件、来源、样式；异源分组；未知保留；明确例外保留 | 接真实 ingest 数据；自动术语词典/字号语义识别未实现，不声称能从聚类断言角色 |
| T2 | 历史参数复用 | 接原 refreshIndex/retrieveCases；索引、案例、规范、工具、结构和源格式门禁；冲突不选赢家 | 工作台纠错到参数库的人工核准闭环；真实案例验证；不自动套历史栏宽或缩放比 |
| T3 | SVG 无头预处理 | 显式字体族映射、多进程、原件保护、缓存复验；复杂结构拒绝 | 字号、最终线宽、色彩和实际墨迹仍由现有工具/求解器处理；真实原生验证 |
| T4 | 测量证据接口 | pt/px、DPI、原点、页号、误差、来源指纹统一；不把像素当文字语义 | 与另一 AI 的求解器确认接口；真实测量采集器接入 |
| T5 | 增量失效与冻结保护 | 依赖和共享画板失效传播；冻结项要求副本；被移除项不自动删除 | 实际依赖图与旧局部渲染器联调；不是新局部重绘引擎 |
| T6 | 按类批处理 | 类别+路线+格式+策略分组；保留文章身份；已完成/已验收保护；固定入口串行调度；旧方案和文件hash复验 | 本机唯一写入者确认、真实 Adobe 副本运行、工作台入口、完整自动证据提取 |
| T7 | 按篇完整性与交付 | 明确预期输出集合、终检、重复编号和实际文件hash检查；可选完整性门禁接原交付器 | 目前严格发布为全批阻断；逐篇独立增量发布、真实跨图视觉一致性尚未完成 |
| T8 | 回归与交接 | 本次重跑 Node 107/107、Python 13/13；真实双进程 SVG 测试；模拟原生适配器测试 | 原仓库全量回归、Windows/Adobe/PDF 实测、真实墙钟提速、正式发行 |

## 本次继续时新增的保护

已制作待复核输出不再重复入队。运行返回 0 后，还要核对记录里的实际方案内容；旧字号、旧文字即使 sourceHash 相同也不能冒充本次结果。恢复任务会再次检查当前台账、方案、原生记录与三类输出文件，而不是只看“上次成功”标签。

## 修改范围

新增 `collaboration/batch/` 模块和说明、新增两份 Node 测试与一份 Python 测试、新增 `plan-batch.mjs` / `run-batch.mjs`。已有文件只改 `collaboration/scripts/sync-delivery.mjs` 的可选门禁和 `package.json` 的测试命令，另更新本清单。

不修改通用求解器、`lib/fit.mjs`、`lib/ink-label-layout.mjs`、`lib/path-containment.mjs`、`adobe/`、`production-runtime/`、`pinned-releases/`、`RELEASE.json`、已安装 Skill、全局 HANDOFF、真实作者数据或验收标记。

## 验证命令

```sh
npm run test:batch
python -m unittest discover -s collaboration/tests -p test_svg_headless.py -v
```

107 项 Node 测试中的原生适配器测试明确使用 synthetic/simulated 数据，不是 Adobe 实测。没有生产提速比例结论。详见 [模块接口与接续说明](collaboration/batch/README.md) 及 [验证记录](collaboration/batch/VALIDATION-20261014.json)。

## 下一阶段的顺序

先在本机复核既有 P0 验收绑定与唯一写入者交接；再选择未验收图件副本，把现有 ingest/预检证据接进新报告；先 dry-run，再串行原生验证；最后接工作台和按篇增量发布。不能批量补 passed/accepted 来强行入队或交付。
