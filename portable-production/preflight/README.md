# 期刊图件前置筛选 v2 — 已迁入 portable-production

面向现有对话／Agent 的证据提取与生产路由，不是新上传网站，不是正式PDF制作器。

```sh
python -m pip install -e '.[test]'
python -m journal_preflight probe input-manifest.json --out candidate-probe
# 由Agent查看原图/证据并给出review.json，不是让用户量坐标。
python -m journal_preflight route candidate-probe/probe.json review.json --manifest input-manifest.json --out screening.json
python -m pytest -q
```

输入清单示例（使用原文件实际路径）：
```json
{"files":[{"id":"paper-a","path":"/data/paper.docx"},{"id":"source-a","path":"/data/figure.svg"}]}
```

程序支持 DOCX、PDF、SVG（含draw.io压缩或非压缩mxGraph元数据）、单帧PNG/JPG/TIFF/WebP；其他格式明确标成 unsupported。后续新增PPTX/Office解析可接相同接口，当前不宣称已经支持。输出：probe.json、可追溯原生结构、媒体、匹配候选。筛选字段见schema文件；接入约束见docs/INTEGRATION.md。

另有独立的[逐图加工决策与作者问题契约 v1](docs/EDITORIAL-ROUTE-V1.md)：校验来源哈希、证据引用、显式用户修改历史及保留原文的问题台账。它只提供候选加工前的保守门禁，不自动判断图种、不认证语义，也不替代现有发布或终审流程。

身份/内容配对由Agent视觉核对后另存review；文内图号不由附件名决定。未使用原生语义时保持未知，不生成假连接。已确认栏宽保留，所有版面实测及正式验收另行进行。

没有扫描字体、调用Adobe、外部模型或OCR。核心已迁入本仓 portable-production/preflight；旧独立候选仅保留来源历史。本次整合不修改生产 runtime。依赖软件仍适用各自许可证。

实际路由CLI必须提供当前输入清单重新核对原文件哈希；仅旧probe与旧review相互一致不算当前源核实。Python API不传manifest时单列live_source_snapshot待核，不能正式下发。桥接保留同一建议的历史，冲突栏宽另加门禁，不改原确认值。

来源为分支 `task/preflight-v2-agent-20261015` / PR #4。六个核心及测试文件与已迁入版本完全相同，schema 以后续主线演进为准，不重复合入旧 candidates 目录。批处理 PR #3、约束求解和未验证语义自动识别继续保留候选；正式入口仍按现有来源绑定与审核门禁运行。

## 首次路线建议（实际配对证据输入）

`python -m journal_preflight suggest-route source-review.json --cases paired-cases.json --out new-proposal.json`

可选 `--user-override user-override.json`，输出只新增、不覆盖。Python 公共入口为
`journal_preflight.route_suggestion.suggest_route(source_review, cases, user_override=None)`。
此入口不要求先知道加工方法，不修改旧 JS 检索器，不执行 OCR、不按扩展名判图种。

`source-review.json` 必须由 Agent 阅读实际原图、Word/Links 及上下文后填写：

```json
{
  "source_snapshot": {"source-id": "<实际SHA256>"},
  "structure": "plot",
  "text_requirement": "replace",
  "data_preservation": "required",
  "topology": "not_applicable",
  "evidence": [{"source_id": "source-id", "source_sha256": "<实际SHA256>",
    "location": "<具体页/图/区域>", "observation": "<实际观察及文字、数据保护需求>"}]
}
```

structure 可为 `node_link/plot/photo/ui/mixed/unknown`；文字需求为
`none/preserve_native/replace/unknown`；数据保护为 `required/not_applicable/unknown`；
拓扑为 `reconstructable/not_reconstructable/not_applicable/unknown`。证据覆盖所有来源。
只有联合事实足够时才建议重建、保留数据换字或整图灰度；混合图需显式拆分审查，不能强套。
文字审核中若UI仍有需换字的外加轴、图例或标注，整体不得填 preserve_native。

`paired-cases.json` 是本地已逐项配对的案例数组，每项结构如下：

```json
{
  "id": "<案例ID>", "paired": true,
  "hashes": {"source": "<原图SHA256>", "word": "<WordSHA256>", "final": "<正确参考SHA256>"},
  "structure": "plot", "observed_method": "plot_reletter",
  "method_basis": "observed_difference",
  "scope": "<只在哪些部分观察到该处理，不外推>",
  "observation_evidence": ["<实际配对证据位置、前后差异或历史记录引用>"]
}
```

`method_basis` 必须区分 `observed_difference`（由前后差异推断）与
`historical_record`（历史记录明确记载）；后者也不代表程序认证记录真伪。
案例不按 method 预筛选；差异案例返回 contrast_only，不能强当相同案例。
无适用案例会留下比较审核阻断项。输入哈希与观察绑定只是记录校验，此入口不读取或认证
历史文件内容；仍须下游编辑契约实时核对源文件、实际制作和PDF审核。

用户覆盖对象为 `{"route":"<路线>","provenance":{...}}`，provenance 沿用编辑契约的
actor/user、reference、quote、带时区recorded_at和当前source_snapshot。最终候选保留用户路线；
与事实冲突时留下阻断项，不偷偷改回。输出始终 `ready_for_processing: false`，不会生成
`recorded_satisfied` 或自动验收。它解决首次比较与建议，不替代用户/Agent审核。

正式 Localflow 的 review/publish 已通过编辑契约强制检查每图 `source_review` 与
`text_review`：前者使用上面的 source-review 格式，哈希范围必须与该图 sources 完全一致，
文字需求也必须一致。缺失结构审核、未知事实、或节点结构/统计图事实与纯灰度路线冲突，
都不能放行。旧 preflight `route` 只产候选，其字体/PDF检查仍待核；不能把它或
suggest-route 的输出直接当正式制作审核通过。
