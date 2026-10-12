# 三方 JSON 状态接收工具

`merge.mjs` 只处理四种实际台账结构：`inventory` 的 `articles[]`/`figures[]` 按 `id`，`production-results` 的 `articles`/`figures` 按对象键，`author-templates` 按根文章 ID，`figure-classification` 的 `cards[]` 按 `id`。其余数组（包括子图、反馈附件、分类 history）若两边都改成不同内容，会报冲突；不会按数组顺序猜测对象身份。重复卡片/文章/图件 ID 直接拒绝。

同一图件的 `status`、`userFeedback`、`userAcceptance`、`userAcceptedAt` 等审核字段，若本机与 incoming 双方都变化且结果不同，即使改的是不同字段也报语义冲突；冲突草案保留本机审核字段。已有字段或记录被任一侧删除一律报 `deletion-requires-review`，不会自动执行删除建议。无冲突时，本机新反馈与 incoming 的不同生产字段可以并存。输入支持 UTF-8 BOM。

默认只读 dry-run，JSON 冲突报告写到标准输出，不生成合并文件。示例：

```powershell
node merge.mjs --kind production-results --base base.json --local home-current.json --incoming incoming.json
```

有跨机绝对路径时，接收方明确给映射规则，可重复 `--map-prefix OLD=NEW`；它只在内存中转换 incoming 候选，原包字节不动。最长旧前缀优先，路径分隔符差异比较时视为同一路径。示例：

```powershell
node merge.mjs --kind production-results --base base.json --local home-current.json --incoming incoming.json `
  --map-prefix 'F:/2026年10月=E:/期刊AI生产-家庭接手-20261011/data/2026年10月' `
  --map-prefix 'C:/Users/xdxxk/Documents/Codex/2026-09-20/i=E:/期刊AI生产-家庭接手-20261011/workspace'
```

仅在 `conflictCount=0` 且路径核验通过后，用 `--apply --output 候选新路径.json` 写候选；输出不得与任何输入同路径，已有文件也拒绝覆盖。即使应用成功也**不会写正式台账**：请先核候选、源文件 hash、用户反馈和分类 revision，再由唯一生产者按项目锁与发布流程接入。存在冲突时 `--apply` 仍不写文件，命令退出码 2；参数或结构错误退出码 1。

实际接收时以当前本机文件为 local 重跑，保留新反馈；标为 referenceOnly 的文件不应用。新共同基线必须由接收机实收回执确认后生成，不能用基线副本模拟替代接收机现况。

聚焦测试：`node --test merge.test.mjs`。12项覆盖不同字段、同字段冲突、新图/卡片、反馈本地保留、验收与新问题语义冲突、单边删除、重复 ID、未知数组、UTF-8 BOM 和冲突禁止写文件。工具只依赖 Node 标准库。
