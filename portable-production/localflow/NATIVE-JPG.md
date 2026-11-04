# 原生 JPG 候选与受保护交付

`render-raster` 在普通 `probe` 之后运行，不把原生 JPG 包装成 PDF。此路线只做完整画布灰度转换，保留像素尺寸和长宽比，不裁剪、铺底、重采样、锐化、改变对比度或替换文字。JPEG 使用质量 95，仍是有损格式；无损 PNG 与审计回执保存在候选目录。非不透明来源不能静默转 JPG。

## 输入

制作说明使用 `author`、`author_rel`、`figure_number`、`processing_method: "full-canvas-grayscale"`、`sources: [{"path": "相对路径", "sha256": "来源哈希", "role": "source"}]`，以及 `policy: {"column": "single"}`。默认宽度 80 mm；非默认宽度必须同时设置 `policy.width_mm` 和完全匹配的 `confirmed.width_mm`，不能只由制作说明覆盖。只改变物理分辨率元数据，不增加像素。

`source_path` 明确指定 `sources` 中用于转换的一个图像来源。只有一个来源时可以省略；多个来源时必须显式给出。其他来源可用作 Word、图题或配对上下文，全部保留哈希绑定且逐次复核，不猜测配对，也不从上下文重绘数据。

约束 `confirmed` 须包含：

- `backend: "raster-preprocess"`、`output_format: "jpg"`、`processing_method: "full-canvas-grayscale"`、`column: "single"`。
- `split: "single"` 或 `"multi"` 和匹配的 `expected_outputs`，输出身份与 PDF 路线相同。
- 发布前必须有 [编辑路由契约](EDITORIAL-GATE.md) 的 `editorial_route_contract`、`editorial_figure_id` 和完整 `editorial_targets`。图件路线为 `raster_grayscale_single_column`。

默认交付文件名是 `作者-图N.jpg`。显式 `target_basename` 可使用 `.jpg` 或 `.jpeg`，但必须在约束、审阅和发布调用中完全一致，不能含目录或更换图号。原生 JPG 路线拒绝显式 `.pdf` 文件名。

## 命令

```sh
python -m localflow --config /external/config.json probe /external/manifest.json
python -m localflow --config /external/config.json render-raster /external/spec.json --constraints /external/constraints.json --probe-id PROBE_ID
python -m localflow --config /external/config.json review CANDIDATE_ID --record /external/review.json
python -m localflow --config /external/config.json publish CANDIDATE_ID --author-rel editor/author --figure-number 1
```

`review` 仍必须绑定候选、输出、约束及完整来源哈希，并记录内容与视觉复核证据。它不会授予人工终检。发布前重新从来源复算灰度 PNG 与 JPEG，检查实际字节、像素尺寸、EXIF 物理栏宽及编辑契约，不只相信报告中的通过标志。

发布先生成临时副本，核对哈希与实际图像，再次核对来源、候选、审阅和目标后原子替换。已有异哈希目标必须显式传入 `--expected-target-sha`，旧版外置归档；同图号的其他 PDF/JPG/JPEG、大小写或 Unicode 等价文件名冲突一律阻断，不能借此迁移格式。原始来源和已人工终检文件不可覆盖。

明确人工终检后才调用 `accept`。不指定格式时只能选择唯一的同图号 PDF/JPG/JPEG；也可指定 `--output-format jpg`，以及已明确的 `--author` / `--target-basename`。机械检查通过、内部复核、发布候选和人工终检始终分开。

## 边界

不需要字体文件或 Adobe。候选校验固定绑定渲染源码及 Pillow/PyMuPDF 版本，升级后应重新生成，而非重写旧回执。编辑契约验证记录完整性和来源绑定，不认证所填证据的真实性；仍需实际视觉、语义、InDesign 置入和印刷验收。PNG 仅是内部无损中间产物，本入口不新增其他交付格式。

### Deployment boundary: one state root per delivery root

All writers for a delivery directory MUST use the same `state_root`. The current
writer lock is scoped to that state root, not to the delivery directory. Two
independent state roots targeting the same delivery root are unsupported and can
race between target checks and replacement. This is a deployment constraint,
not an implemented cross-state concurrency guarantee; deployers must verify the
one-to-one configuration before enabling multiple workers.

Review and publication bind to the current sealed candidate's author directory,
figure number and resolved explicit filename. Membership in a batch's
`expected_outputs` alone never permits assigning one candidate to another figure.

### PDF font-policy publication gate

The PDF review/publish boundary now recomputes the existing font-policy evidence
from the sealed spec and measured report. It requires an actual default 8pt
starting layout or a source/reply/size-bound explicit policy exception. A 6–8pt
final-size range, or a visual-approval claim alone, is not sufficient. Low-level
6–8pt preview rendering remains available; native JPG is not subject to vector
font-size gates. This does not authenticate the author of an exception record,
prove all source semantics, or replace external approval verification.

For the current `plot_reletter` route, publication additionally requires the
specialized `chart` renderer and both `xtitle`/`ytitle` semantic roles with nonempty,
successful actual-PDF axis-title checks. A generic `scene` of `label` objects can
no longer pass by producing an empty but vacuously successful axis audit. This
bounded route does not yet support axis-free or partially titled charts; those
must remain unresolved, not be relabeled merely to bypass this gate. The routing
contract still records reviewed classification rather than independently proving
that classification from the source.

An exception's source hash must identify one of the candidate's verified
`spec.sources`; agreement between two copied provenance fields is insufficient.
Regression coverage includes stale-source rejection and matching-source exception
publication through a real PDF chain, as well as a real specialized-chart
publication positive. Caller records still are not independent approval identity
or reconstruction of an absent semantic reply.
