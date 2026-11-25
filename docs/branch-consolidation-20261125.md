# 2026-11-25 仓库优化与双线合并说明

本轮在 `merge/unified-production-20261125` 分支完成对 `origin/main`（`87ba08a`）之后两支并行分支的统一整合，并完成全仓分支盘点与结构整理。

## 一、 双线合并决策与冲突解决

| 维度 | 合入来源 | 最终口径 |
|---|---|---|
| 规则单一源与无头生产 | `origin/cursor/headless-rules-refactor-a87d` | 保留 `rules/journal-rules.yaml`、`portable-production/production_rules/`、`portable-production/headless/`、`tests/golden/` 与 `journal produce --input` |
| 留白策略与测量算法 | Track B（规则）+ Track A（算法） | 严格遵循 2026-11-24 决定：仅读 `margin_pt: 0.25`（拒绝 `0..12pt` 任意覆盖），同时保留 `draft/r49-padding-on-r48-20261110` 的 **1200 dpi** 测量、最多 4 轮逐边补偿（`0.065pt` 容差）与留白后 `export_column_width` 复检 |
| 11-12 作图共性规则 | `origin/draft/figure-common-rules-20261112` | 保留括号正体、自产矢量与图例样线统一 0.5pt、`straighten_connections` 默认框边中心直连、`auto-inside` 优先图内图例 |
| 11-24 确认规则增量 | `origin/cursor/headless-rules-refactor-a87d` | 保留 `never_fill_column`、简单统计图 60mm 起排、`column=auto` 先缩至 6pt 再换行重排再升档、3mm 居中汇总总线（1.5+1.5mm 与 `bus_leg_arrow_scale`）、单位斜杠词表与严格子图命名 |
| 交付保真与命令行 | `origin/fix/production-fidelity-20261110` | 保留 `capacity` 容量检查、`source_route_contract`、`delivery-checklist` 与 `journal package` / `journal capacity` |

## 二、 远程分支清理与归档盘点

仓库共约 40 个远程分支，经逐一核对（截至 2026-11-25）：

1. **可直接删除（约 30 个，领先 `origin/main` 为 `+0`）**：
   - 包括 `release/20261104-clean-move`、`feat/workbench-*`、`fix/integrate-padding-and-delivery`、`fix/original-asset-reference-20261030`、`feat/source-chart-audit-20261029`、`feat/edge-ports-20261029`、`feat/pdf-prescan-evidence-20261028`、`integrate/november-figure-tools-20261028`、`feat/checkbox-glyph-20261027`、`fix/numeric-tick-audit-20261027`、`release/r36-figure-audit`、`integration/verified-main-20261026`、`fix/pdf-stream-audit-20261026`、`dot/bounded-figure-production-20261022`、`fix/bilateral-tree-layout`、`release/r32-production-baseline-20261020`、`release/r31-public-capabilities-20261020`、`closeout/portable-production-20261016`、`experiment/optimizations-20261014`、`release/r21-handoff-20261014`、`fix/unified-layout-20261013`、`task/release-consolidation-20261013`、`task/office-sync-baseline-20261013`、`task/review-three-properties-20261013`、`handoff/home-20261013-001335`、`task/batch-rework-preflight-20261012`。
2. **本次已合入或已完全覆盖（合并到 `main` 后可删除）**：
   - `fix/production-fidelity-20261110`、`draft/r49-padding-on-r48-20261110`、`draft/figure-common-rules-20261112`、`cursor/headless-rules-refactor-a87d`
   - `docs/workspace-rules-20261102`、`docs/clarify-workspace-20261102`（文档正文已合入 `main`）
   - `task/preflight-v2-agent-20261015`（`candidates/agent-preflight-v2` 已转正至 `portable-production/preflight/`）
3. **历史实验/停产保留快照（建议转轻量 tag 归档后删除分支）**：
   - `handoff/production-wip-20261014`、`fix/acceptance-bindings-20261014`（见 `HANDOFF.md`）
   - `exp/constraint-layout-solver`、`task/batch-pipeline-20261014`（十月协作试验分支）

## 三、 运行时一致性巡检

新增只读检查脚本 `scripts/check-runtime-parity.mjs`（`node scripts/check-runtime-parity.mjs`），用于持续观测根目录 `lib/`、`adobe/`、`scripts/` 与 `production-runtime/`、`pinned-releases/` 的一致与已记录分叉，避免误覆盖历史兼容契约。
