# 期刊 AI 生产工作台

## 2026-10-16 现行入口

新制作与续跑先用 [portable-production](portable-production/README.md)：preflight 判定能力，localflow 管理批次索引、路由、候选与保护状态，direct-pdf 统一排版、字体、连接和 PDF 审计。机器路径、字体与生产素材始终放在仓库外。

下述 `production-runtime`、`workbench`、Adobe 和 `collaboration/scripts/run.mjs` 是已发布的原生格式兼容路线；仅在直接 PDF 明确不覆盖或需编辑原 AI 时选用。旧的预确认流程不再是普通新图的前置门禁，现行 Agent 入口以数据化语义回复和实际 PDF 复核闭环。

## 当前整理版本

2026.10.20-r31-public-capabilities，在 r30 基础上纳入已经由真实作图和本机完整回归验证的便携公共能力。现有 `workbench` 完整保留；普通生产仍以 `portable-production` 为主线，工作台与 Adobe 路径继续作为兼容入口。作者私有图件、机器路径、字体文件和过程证据不进入 GitHub。

先读 [当前交付与审核契约](collaboration/20261013-consolidation.md) 和 [本版范围与验证边界](release-notes/2026.10.20-r31-public-capabilities.md)。旧交接是历史证据，不作为当前界面要求。

## 机器入口

配置位于仓库外，参照collaboration/machine-config.example.json：

- 固定工具：`node collaboration/scripts/run.mjs --config <machine.json> status <JOB>`
- 工作台：`node collaboration/scripts/start-workbench.mjs --config <machine.json>`
- 当前交付：`node collaboration/scripts/sync-delivery.mjs --config <machine.json>`
- Skill部署预检：`node collaboration/scripts/install.mjs --config <machine.json>`；明确部署追加`--apply`，保留备份和失败回滚。

排版只取`<deliveryRoot>/当前/排版定稿`；未配置deliveryRoot则位于recordRoot/交付。每次按正式验收、完整子图集合和hash生成，不按“最终版”文件名猜测。旧版撤出当前入口并可恢复归档；不自动删除原稿、审计证据及未知排版链接。

## 生产与协作边界

用户已恢复分栏目集中制作；按最新本地任务表续做，已通过作者不重复核对新版差异。Adobe串行，保留应用和文档；已验收成果不得重制。正式记录由接手回执指定唯一写入者按ID和字段合并，反馈和验收冲突不按时间取胜。

真实原稿、图件、AI/PDF、截图、密钥及机器配置不上传GitHub。当前交付目录是台账的派生副本，不是第二份生产状态权威。交接先暂停、封包、校验并写接收回执，不双机共写运行中的Git、台账和AI。

## 验证边界

本版源码回归和发布包验收以 [验证记录](release-validation-20261020-r31.json) 为准。工作台与 Adobe 渲染器未改动，继续继承 r30 的兼容验证边界；本轮不声称覆盖所有图种，也不把代码测试替代为人工视觉终审或 InDesign 实际置入验收。
