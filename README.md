# 期刊 AI 生产工作台

## 当前基线

2026.10.12-r2。此仓库统一工具、工作台、测试与规范。production-runtime 是逐文件核验的正式运行源码；根目录 lib/adobe/scripts 是研发源码，两者既有差异尚未全面归一，不可互相全量覆盖。RELEASE.json 锁定正式运行文件，部署与任务版本日志保留哈希。工作台使用当前已验收 Git 提交下 workbench/。

## 本机入口

复制 collaboration/machine-config.example.json 到仓库外，按机器实际目录填写。

- 工具：node collaboration/scripts/run.mjs --config <外部配置> status <任务目录>
- 工作台：node collaboration/scripts/start-workbench.mjs --config <外部配置>
- 安装预检：node collaboration/scripts/install.mjs --config <外部配置>
- 明确部署：同上添加 --apply；保留旧文件备份，Adobe 占用时拒绝。

正式资料、权威记录、截图与真实作者回归样例不入 Git；本地样例引用见 references/local-fixtures.json。工作台 classification-assets/images 从接收资料包取得，不入库。配置 workspaceRoot 暂指历史工作区，workRoot 指新的中间产物目录。

## 协作约束

一个问题一个短期分支/worktree；同台 Adobe 串行；探索者不得写正式验收状态、覆盖成品或安装 Skill。正式记录由交接后的唯一生产者按 ID/字段合并。交出方先暂停，接收方校验并写回执后接手。GitHub 私有仓库只管代码与规范，G 盘封包目录的坚果云同步尚须确认。

## 本次验证边界

接收时 82 项针对性静态检查通过；一个真实网络结构图副本在 Illustrator 以 6.5 pt 输出可编辑 AI/PDF并目检。不是所有图型的新原生回归，不宣称生产速度收益。固定目录入口、版本漂移拒绝、安装备份、工作台读取及状态保护做了针对性测试；历史全量测试依赖本机资料和 Adobe，不作为云端自动测试。旧已验收成品未重制。

GitHub 的首次基线只包含经筛选的代码树；较早本地历史含真实作者计划，保留在办公室旧仓库，不上传该历史。examples/ 与 tests/fixtures/ 按引用与哈希本地取用。正式 runtime 保持经 Adobe 验证的原始字节，Git 禁用行尾自动转换以保证跨机 SHA 一致。
