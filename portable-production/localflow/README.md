# 离线本地流程

从源码或下载包的 `portable-production` 目录运行 `python -m localflow --config <包外配置.json> <命令>`。已安装机器的旧 `run.cmd` 继续使用原入口，不随公共包分发。配置必须有 `delivery_root`、`state_root`、`font_profile`、`cache_root`，并明确 `workbench_enabled: false`。状态、候选、预检证据、归档和日志全在交付目录之外。

流程：

1. `catalog`：只读递归索引现有“编辑/作者”与“编辑/0没做完/作者”的文件，按文件 stat 复用哈希。只有作者目录根层的 `作者-图N.pdf/.jpg/.jpeg` 算已有交付；附件仍入索引，不算完成。
2. `audit-pdfs`：只读扫描交付根目录全部 PDF；字体未嵌入、字体描述或有效 `/CapHeight` 缺失、加密、页面旋转和批注会使命令返回非零。该检查也适用于历史稿和非 direct-pdf 来源。
3. `probe <manifest.json>`：manifest 给出 `source_root` 和 `files: [{"id":"...","path":"源目录内相对路径"}]`。同一源内容、ID→路径和预检源码复用快照；复用前重新核对原件与每份证据的哈希。源稿可位于现有作者目录，程序不会写入原件。
4. `route <probe-id> --review <Agent审阅.json> --manifest <当前manifest.json>`：调用 preflight v2 路由并实时核对原件，输出仍是建议候选。Agent 审阅格式遵循 `preflight/docs/AGENT-CONTRACT.md`。复杂图的 Agent `prepare/complete/review` 仍可直接调用引擎既有入口；本 CLI 的 `render` 消费最终制作说明。
5. `render <spec.json> --constraints <已确认约束.json> --probe-id <id>`：约束 `confirmed` 必须有 `split`（single/multi）、`processing_method`、`backend: direct-pdf`、`column`、`expected_outputs: [{"author_rel":"编辑/作者","figure_number":"1"}]`。制作说明必须给出匹配的 `author_rel`、`figure_number`、`processing_method`、来源哈希及栏宽；未知建议可省略，明确冲突会阻断。生成候选并检查引擎实际 PDF 审计、正式字体和当前源。返回候选 ID、PDF、耗时、日志路径和警告条数。
6. `review <candidate-id> --record <Agent核验.json>`：记录须绑定 `candidate_id`、`output_sha256`、`constraints_sha256`、`source_hashes`、`author_rel`、`figure_number`、`reviewer`，以及 `content`、`visual` 两项各自的 `conclusion: approved` 和具体 `evidence` 列表。这是 Agent 内部核验，不代表人工终检。用户无需填写 JSON。
7. `publish <candidate-id> --author-rel <编辑/作者> --figure-number <N>`：只向已存在作者目录写平铺 `作者-图N.pdf`。同哈希幂等；已有异哈希 PDF 默认拒绝，显式 `--expected-target-sha <当前哈希>` 才归档旧版后原子替换。若同图号已有 JPG/JPEG，阻断并要求单独迁移；源绑定原件及已登记人工终检的文件不可覆盖。发布临时副本和 `accept` 目标都会重新读取实际 PDF 字节，检查字体描述中的有效 `/CapHeight`；禁止用普通文件复制绕过发布入口。
8. `accept --author-rel ... --figure-number ... --expected-sha ... --reviewer ... --evidence ...`：人工终检完成后显式登记受保护哈希。`status [candidate-id]` 查看外置状态；状态中 Agent review、发布和人工终检分开。

验证：从 `portable-production` 运行 `python -m pytest tests-local -q`，先将环境变量 `JFW_TEST_FONT_PROFILE` 指向包外的正式字体配置（未设置时使用历史路径 `fonts.local.json`）。测试包含临时目录 probe→真实引擎 render→Agent review→publish→改写拒绝→显式哈希替换及归档→accept 后拒绝覆盖，以及源变化、约束变化、错误图号、预览字体、字体描述缺失和同图 JPG 冲突。字体库警告保存在候选 `render.log`，不影响已通过的实际 PDF 审计。
