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
