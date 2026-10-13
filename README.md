# 期刊 AI 生产工作台

## 当前整理版本

2026.10.13-r7-flowchart-shapes。RELEASE.json锁定正式production-runtime与Skill字节；根目录lib/adobe/scripts为研发树，candidates为未发布试验，不能全量互覆。旧r5固定快照保留回滚。

先读 [当前交付与审核契约](collaboration/20261013-consolidation.md) 和 [版本验证](release-notes/2026.10.13-r7.md)。旧交接是历史证据，不作为当前界面要求。

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

发布回归覆盖固定入口、安装故障回滚、完整交付和当前目录撤回、状态保护、分类审核、原生样式与括号。另有两项真实Adobe副本回归与实际PDF检查；不是所有图种的全量原生回归，也不宣称新速度收益。历史本机样例从外部资料包取得，不进云端CI。
