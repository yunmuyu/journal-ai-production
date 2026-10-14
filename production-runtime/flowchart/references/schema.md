# Illustrator drawing generator schema 3.0

All output is strict JSON for `AI流程图生成器.jsx` 3.0. Flowcharts, block diagrams, signal-flow diagrams, freeform formula diagrams, and statistical charts all use this same Illustrator entry.

A chart with axes, ticks, bars, lines, error bars, confidence bands, or boxplots uses `kind: "statChart"`, not `nodes`/`edges`.

## Formula Typography

All diagram text fields that the Illustrator generator renders as editable text support the same rich-text markers: node `text`, edge `label`, `freeTexts[].t`, and chart text labels.

- Wrap source-visible italic mathematical variables in `$...$`. Do not wrap upright prose or upright constants.
- Use `^` for true superscript and `_` for true subscript. Braces are allowed for multi-character scripts: `$W^q$`, `$W_v$`, `$A=N(0,\sigma^2)$`, `$a_{11}$`.
- Unicode scripts are also accepted: `a₁₁`, `σ²`.
- Numeric scripts remain upright by default. Letter scripts inside `$...$` become italic, so `$W^q$` gives italic `W` and italic superscript `q`, while `$\sigma^2$` gives italic `σ` and upright superscript `2`.
- If the source text is upright, leave it outside `$...$`, for example `B = 0`.

## Statistical Chart JSON

The root chart object is:

```json
{
  "schemaVersion": 3,
  "kind": "statChart",
  "renderMode": "textOnly",
  "charts": [],
  "cols": 2
}
```

Each chart requires:

- `title`: exact visible chart title.
- `yLabel`: exact visible Y-axis label, converting a trailing unit in parentheses to slash form when appropriate, for example `Average Reaction Time (s)` becomes `Average Reaction Time/s`.
- `yMin`, `yMax`, and `yStep`, or numeric `yTicks` listed from bottom to top. For plotted data, the renderer derives `yMin`/`yMax` from the smallest/largest `yTicks` when they are omitted; provide explicit `yMin`/`yMax` when the source range extends beyond the visible ticks.
- `renderMode`: use `"textOnly"` (the default). Statistical-chart output preserves editable text only and omits chart graphics. `textOnly: true` is a compatible alias.

Line chart fields:

- Default chart type is a line plot.
- `xTicks`: numeric X positions from left to right.
- `xTickLabels`: optional visible labels for the numeric X positions, in the same order and length as `xTicks`; use this for categorical line plots such as `Level 1\nGuyu`. Never put category text directly in `xTicks`.
- `series`: array of `{ name, data, marker }`. `data` length must match `xTicks` when data is drawn, and every entry must be a finite JSON number. Do not use `null`, strings, or `NaN` for missing points; split the chart into only drawable numeric series or omit uncertain/sparse marks.
- `drawData`: do not emit this field for normal statistical-chart work. A 流程图生成器 3.0 preserves the text layer without drawing lines, bars, boxes, markers, or error graphics.
- Optional `band`: `{ low: [], high: [], gray: 0.92 }`; `low` and `high` lengths must match `xTicks` and contain only finite JSON numbers.
- Optional `series[].error`, `series[].errorLow`, `series[].errorHigh`: symmetric or asymmetric error bars in Y-axis value units, containing only finite JSON numbers.
- Optional `series[].labels`: value labels near the plotted points.

Bar chart fields:

- `type: "bar"`.
- `xCats`: visible category labels from left to right. Use `\n` only for source-visible line breaks, or `\r` when targeting Illustrator paragraph line breaks.
- `series`: array of `{ name, data, gray }`. Use one unnamed series for a single-color bar chart. `data` length must match `xCats`.
- Optional `series[].error`, `series[].errorLow`, `series[].errorHigh`: error bars in Y-axis value units.
- Optional `thresholds`: array of horizontal reference lines such as `{ y: 80, label: "80% threshold", lineStyle: "dashed" }`.

Boxplot fields:

- `type: "boxplot"` or `type: "box"`.
- `xCats`: visible category labels from left to right.
- `boxes`: one entry per category. Each entry is either `{ min, q1, median, q3, max }` or `[min, q1, median, q3, max]`.

Chart routing rules:

- For a multi-panel statistical figure, put every panel in one `charts` array and set `cols` to the source grid, usually `2`.
- Statistical charts preserve titles, axis labels, ticks, category labels, legends, value labels, thresholds, and annotations as editable text, while axes, grid lines, bars, lines, bands, boxes, markers, and error bars are omitted. This is implemented directly inside A 流程图生成器 3.0; do not call `画折线图.jsx`.
- Preserve figure labels like `Fig.1`, `Fig.2`, `(a)`, `(b)` inside `title`.
- Preserve visible threshold labels, value labels, and units. Do not invent values that are not visible or inferable from the figure.
- Use grayscale only; do not encode color as a requirement.
- Validate with `node scripts/validate_flowchart.js <output.flowchart.json>` and deliver only a PASS result.

## Flowchart JSON schema

The root object is:

```json
{
  "schemaVersion": 3,
  "kind": "flowchart",
  "widthClass": "single",
  "nodes": [],
  "edges": []
}
```

Root fields beyond `nodes` and `edges`:

- `kind` (required): `flowchart` for flow logic, `blockDiagram` for hardware/system blocks, `signalFlow` for communication/control signal diagrams with operator circles and external ports, `freeform` for text/symbol diagrams without semantic boxes, or `statChart` for statistical charts. `blockDiagram`, `signalFlow`, `freeform`, and `statChart` require schema version 3.
- `widthClass`: `single` (default, 80 mm maximum) or `double` (use available artboard width). Decide after semantic wrapping and the generator's calibrated natural-layout estimate at the required 8 pt size. Three columns, long labels, or Latin-heavy text are not automatic `double` triggers. Use `single` whenever compact spacing and natural phrase breaks keep the complete diagram within 80 mm; use `double` only when the measured layout still exceeds 80 mm or creates excessive line stacking.
- `fontSize`: optional strict point size: `8`, `7`, or `6`. When present, the renderer uses exactly this size rather than trying smaller sizes to fit the available layout. Use `8` whenever the source typography is 8 pt.
- `layoutMode`: `standard` (default) or `compact`. Compact changes sibling column spacing, never the required 3 mm connector length. For a source-visible dense composition, `compact` is the faithful default; `standard` requires visible source evidence of the larger breathing room.
- `treeLayout`: optional named semantic contract for schema-v3 `flowchart`; currently only `module`. Use it for a source-visible three-level module hierarchy with one root row, one module-title row, and one vertical terminal-leaf row. It requires `layoutMode:"compact"`, `flowShapePolicy:"sourceVisible"`, and `fontSize:8`; all hierarchy edges must explicitly use `arrow:"none"`. See the module-tree contract below.
- `swimlaneLayout`: optional `vertical` or `horizontal`, only for schema-v3 `flowchart`. `vertical` creates left-to-right lanes with shared top/bottom bounds and one common header band; `horizontal` creates top-to-bottom bands with shared left/right bounds, continuous horizontal dividers, and a left label divider.
- `sideLabelBand`: optional `layerLabels`, only for schema-v3 `blockDiagram`. It reserves a real 15 mm band to the left of the aligned content frames so source-visible layer names do not overlap frames or get lost when empty grid columns are normalized.
- `flowShapePolicy`: for `flowchart`, `endpointsRounded` (default) draws every non-decision entry/sink node as a rounded terminator and every other ordinary node as a square-cornered `process`; `sourceVisible` preserves the per-node `shape` declarations. Decisions and ellipses are never rewritten by this policy.
- `containers`: semantic outer frames, described below.
- `stacks`: independent vertical chains, described below.
- `horizontalStacks`: independent same-row chains, described below.
- `freeTexts`, `freeLines`, `freeDots`: optional freeform overlay layers, described below. They can be mixed with normal `nodes`/`edges`, or used alone with `kind: "freeform"` and an empty `nodes` array.
- `ratio`: for pure `freeform` diagrams, optional canvas height/width ratio. Default is `0.66`.

Version policy:

- Use `schemaVersion: 1` only for simple acyclic top-to-bottom diagrams. The generator remains backward compatible with existing version 1 assets.
- Use `schemaVersion: 2` for feedback loops, side-exiting decision branches, or non-default merges. Version 2 adds edge ports and label placement without adding freehand coordinates.
- Use `schemaVersion: 3` for generator 3.0 features: `kind: "blockDiagram"` / `"signalFlow"` / `"freeform"`, compact layout, containers, equal-size groups, independent vertical stacks, row/column spans, ellipses, signal operators, declared via routes, arrow modes, segment labels, free positioned text, free line arrows, and free dot rows. Versions 1 and 2 remain supported.

Module-tree contract (`treeLayout:"module"`):

- The graph has exactly one root, one row of module-title nodes, and one terminal row of leaf nodes.
- Every leaf uses `textDirection:"vertical"`, shares one `heightGroup` and one `widthGroup`, and occupies the same `row`.
- Every module title shares another `heightGroup`, occupies the same `row`, and connects directly only to leaves.
- A module title `column` equals the midpoint of its leftmost and rightmost child columns. The root `column` equals the midpoint of the leftmost and rightmost leaf columns. Half-columns are required when the midpoint is fractional.
- Consecutive sibling leaf groups keep an unused column only when the source visibly shows that larger separator; compact source trees keep adjacent tracks.
- Every edge explicitly sets `arrow:"none"`. The general omitted-arrow default is `end`, so omission would add incorrect black arrowheads.
- Do not add `containers` unless the source visibly draws grouping frames.
- A graph matching the single-root/module-row/vertical-leaf signature is rejected unless the root declares `treeLayout:"module"`; this prevents a valid-looking JSON from taking the wrong ordinary-grid renderer.

Use `kind: "freeform"` when the source is primarily positioned text and symbols, such as a matrix, formula schematic, axis labels without plotted data, or a diagram that must preserve typography before semantic geometry. In pure freeform diagrams, `nodes` may be empty if `freeTexts` is non-empty.

Each node requires:

- `id`: unique ASCII identifier matching `^[A-Za-z][A-Za-z0-9_-]*$`.
- `text`: exact visible wording. Use `\n` for intentional line breaks. It may be empty only for signalFlow `multiplier`, `summer`, and invisible `port` nodes because their vector glyph or endpoint is generated by the renderer.
- `shape`: `terminator`, `process`, `decision`, schema-v3 `ellipse`, `cylinder`, `arrow`, `brace`, `plusCircle`, `minusCircle`, blockDiagram-only `label`, signalFlow-only `functionBlock`, `multiplier`, `summer`, `port`, or schema-v3 `waveBlock` / `sideCurveBlock`. `process` is the ordinary straight-corner editable rectangle, including normal signal-flow text blocks. `waveBlock` preserves the source-visible compact block with straight top/sides and one curved lower edge; `sideCurveBlock` preserves the source-visible compact block with inward-curved left and right ends. Both are native editable paths and are only used when the source visibly has that primitive; they must not replace ordinary rectangles. `label` is editable text without an independent border; use it for a title or divider caption printed directly inside a visible outer frame, and never use it as an edge endpoint. `cylinder` is the fixed database/storage primitive from the existing `画圆柱.jsx` family: thin top ellipse, straight sides, and a curved lower edge. It is not an ordinary text-sized rectangle and must not be approximated with `ellipse`; `arrow` is the editable block arrow from `画箭头.jsx`; `brace` is the editable brace from `画大括号.jsx`; `plusCircle` and `minusCircle` are native circle operators. `functionBlock` is reserved for a source-visible rounded functional box; `multiplier` is a circle with editable vector `×`; `summer` is a circle with editable vector `+`; `port` is an invisible external endpoint for a source/sink arrow. With the default `flowShapePolicy`, ordinary flowchart nodes are normalized from their graph position: entry/sink nodes become `terminator`, interior steps become `process`, and `decision`/`ellipse` stay unchanged. Use `sourceVisible` only when the source deliberately needs a different shape. In `blockDiagram`, ordinary data, device, library, and result blocks use `process`; reserve `terminator` for a visibly rounded start/end-style shape.
- `row`: non-negative integer; top is `0`.
- `column`: non-negative integer or half-integer; left is `0`.

Optional node field:

- `textDirection`: `horizontal` (default) or `vertical`. Vertical means stacked editable characters, never rotated text.
- `arrowDirection`: only for `shape:"arrow"`; `right` (default), `left`, `up`, or `down`.
- `arrowHeads`: only for `shape:"arrow"`; `end` (default) or `both`. A two-headed arrow remains an editable polygon; put its visible label in the node `text`, which the renderer positions as separate text above the arrow.
- `braceSide`: only for `shape:"brace"`; `left` (default), `right`, `top`, or `bottom`. `left`/`right` draw a vertical brace; `top`/`bottom` draw a horizontal brace. For the two opposing horizontal braces between `B = 0` and `$A=N(0,\\sigma^2)$`, use `bottom` for the upper brace and `top` for the lower brace.
- `heightGroup`: ASCII ID. Every node in the same group is raised to the tallest text-driven height in that group.
- `widthGroup`: ASCII ID. Every node in the same group is widened to the widest text-driven box in that group.
- `rowSpan`, `columnSpan`: positive integers. Use only when the source visibly contains a block spanning multiple grid tracks. Spanning nodes require an integer `column`.

Each edge requires:

- `to`: target node or container ID. Use a container ID when the visible connector terminates at the outer frame rather than at an internal member.
- Exactly one source form:
  - `from`: source node or container ID; or
  - `fromEdge`: the `id` of an earlier edge when this connector visibly branches from that line.
- Exactly one target form:
  - `to`: target node or container ID; or
  - `toEdge`: the `id` of an earlier edge when this connector visibly merges into that line.

Optional edge field:

- `id`: unique ASCII identifier. Required when another edge uses this edge as `fromEdge`.
- `fromEdgePosition`: currently only `middle`; required with `fromEdge`. A line-derived branch is automatically orthogonal and may not use `straight` or `via`.
- `toEdgePosition`: currently only `middle`; required with `toEdge`. A line-derived merge is automatically orthogonal and may not use `straight` or `via`.
- `label`: exact branch label such as `是` or `否`. When the decision text is Chinese, use Chinese truth labels and reject `T/F`, `True/False`, `Y/N`, and `Yes/No` unless the source explicitly presents code notation that the user asks to preserve.
- `fromPort`: `top`, `right`, `bottom`, or `left`.
- `toPort`: `top`, `right`, `bottom`, or `left`. Set it together with `fromPort`.
- `fromPortPosition`, `toPortPosition`: `center` (default), `upper`, or `lower` on a left/right side; `center`, `left`, or `right` on a top/bottom side. Use these named anchors when parallel routes must leave or enter different parts of one side.
  Opposing top/bottom sides with overlapping horizontal spans are automatically aligned to one vertical connector, and opposing left/right sides with overlapping vertical spans are aligned to one horizontal connector. A connector therefore does not have to start or end at the side midpoint. Use explicit positions only when the source visibly requires a different attachment point.
- `labelPosition`: `source` (default for decision branches), `middle`, or `target`.
- `arrow`: `end` (default), `start`, `both`, or `none`.
- `via`: non-empty array of semantic orthogonal waypoints. Each waypoint has `x` and `y`. A numeric `x` is a column coordinate; numeric `y` is a row coordinate; `"from"` and `"to"` reuse that axis from the source or target port. `"from+gap"`/`"from-gap"` and `"to+gap"`/`"to-gap"` offset that axis by exactly 3 mm in Illustrator coordinates, where positive Y is upward. Therefore outward source legs are left=`x:from-gap`, right=`x:from+gap`, top=`y:from+gap`, bottom=`y:from-gap`; target-side approach points are left=`x:to-gap`, right=`x:to+gap`, top=`y:to+gap`, bottom=`y:to-gap`. Numeric values may be integers or half-integers and may be negative for an outer lane.
  The first waypoint must preserve either the source X or source Y coordinate, and the last waypoint must preserve either the target X or target Y coordinate. Add an intermediate waypoint for every right-angle turn; never let one segment change both axes.
- `labelSegment`: zero-based route-segment index.
- `labelSide`: `above`, `below`, `left`, or `right`. Use with `labelSegment`.
- `lineStyle`: `solid` (default), `dashed`, or `dotted`. The calibrated dash arrays are `dashed: [4, 3]` and `dotted: [2]`; arrowheads remain solid.
- `routeStyle`: `orthogonal` (default) or schema-v3 `straight`. `straight` is valid in `blockDiagram` and `signalFlow`, requires explicit ports, connects those two side centers with one segment, and cannot be combined with `via`.
- `routeLane`: schema-v3 positive integer for a no-`via` same-side feedback loop. `1` uses the nearest local 3 mm lane, `2` the next local 3 mm lane, and so on. It keeps parallel returns compactly beside their endpoint boxes instead of extrapolating a distant numeric grid column. A same-side edge with `via` is invalid because independently expanded source/target legs can reverse direction before the arrow.
- `shaftLength`: `"2mm"` or `"3mm"`. Use `2mm` only when the source visibly uses the shorter compact side connector; use `3mm` when the selectable line shaft between Arrow 5 centers must measure exactly 3 mm. The generator enlarges the endpoint boundary gap by one half-arrow depth for each attached arrow, then trims the line to the arrow centers.

Example declared route:

```json
{
  "from": "source",
  "to": "target",
  "fromPort": "bottom",
  "toPort": "left",
  "via": [
    {"x": "from", "y": 0.5},
    {"x": 1.5, "y": 0.5},
    {"x": 1.5, "y": "to"}
  ]
}
```

Each container requires:

- `id`: unique ASCII identifier.
- `members`: non-empty array of node IDs.
- Optional `padding`: `minimal` (1 mm), `tight` (3 mm, default), or `normal` (6 mm).
- Optional `sizeClass`: `wideNested` for a one-member frame-within-frame pattern. It requires exactly one member and fixes the outer visible frame to 183.5 x 34.4 pt while keeping the inner box text-driven.
- Optional `lineStyle`: `solid` (default), `dashed`, or `dotted`. The calibrated dash arrays are `dashed: [4, 3]` and `dotted: [2]`.
- Optional `cornerStyle`: `square` (default) or `rounded`. Rounded containers use the calibrated 5 mm frame radius.
- Optional `label`: visible container title.
- Optional `labelPosition`: `topCenter` (default) or `bottomRight`.
- Optional `frameGroup`: named alignment group. Containers in the same group share the same left and right frame bounds; use it for layered architectures whose main section frames are visibly aligned and equal-width.
- Optional `memberDistribution`: `spaceBetween`. After the frame group is resolved, members in one visual horizontal row are redistributed from the inner left edge to the inner right edge with equal intervening whitespace. Every member must share the same `row`; do not use it on a multi-row layer or on a container that mixes a device row with a caption row, because the renderer will lay those members out as one horizontal sequence. Apply it only when the source visibly fills the frame; otherwise it creates artificial density loss. A nested inner frame around the same members follows their final positions automatically.
  A `bottomRight` label makes the vertical padding asymmetric: the unlabeled top band is 2 mm above the topmost member, while the normal lower padding remains available for the label. This applies to both single-member and multi-member containers.
  When two adjacent containers visibly share one divider band or caption, include the same `label` node in both `members` arrays. The renderer suppresses duplicate boundary padding and lets the two frames overlap at that shared member.

Vertical swimlane contract (`swimlaneLayout:"vertical"`):

- `containers` are lane declarations in visible left-to-right order, not ordinary wrapping frames.
- At least two lanes are required. Every lane has a non-empty `label`, and every node belongs to exactly one lane.
- Lanes are drawn as one square-cornered outer rectangle, one full-width header separator, and `lane count - 1` internal vertical dividers. They share one top edge, one bottom edge, and a dedicated 7 mm header band; separate overlapping lane rectangles are forbidden.
- Do not set `frameGroup`, `memberDistribution`, `labelPosition`, or rounded `cornerStyle` on lane containers. Use node `column` values to preserve the lane order and use half-columns only for source-visible side branches inside one lane.
- Use ordinary `containers` without `swimlaneLayout` for nested frames, local group boxes, and unrelated titled regions that should shrink around their own members.

Horizontal swimlane contract (`swimlaneLayout:"horizontal"`):

- `containers` are band declarations in visible top-to-bottom order, not ordinary wrapping frames. At least two bands are required, every band has a non-empty `label`, and every node belongs to exactly one band.
- Bands are drawn as one square-cornered outer rectangle, continuous horizontal dividers, and one continuous left label divider. The renderer never draws one overlapping rectangle per band.
- The left label column is reserved by the renderer; place band labels in `label` and do not fake the column with empty nodes or `freeLines`. Use optional `labelDirection:"vertical"` when the source visibly stacks the band label one character per line; the default is `"horizontal"`.
- Do not set `frameGroup`, `memberDistribution`, `labelPosition`, or rounded `cornerStyle` on band containers. All bands must use the same `lineStyle`; the calibrated styles are solid, dashed `[4, 3]`, and dotted `[2]`.

Each vertical stack requires:

- `id`: unique ASCII identifier.
- `members`: at least two node IDs in top-to-bottom order. A node may belong to only one stack.
- Optional `gap`: `standard` (3 mm, default) or `minimal` (1 mm).
- The first member keeps its row anchor. Every following member is placed by the declared visible edge gap, independently of taller nodes in adjacent columns.
- Use a stack for each independent chain of three or more nodes in a multi-column flowchart unless the source visibly aligns corresponding nodes across chains. A shared ordinal depth is not a visual rank.
- A stack must not jump across a fan-out/fan-in layer. When an earlier member connects to one or more intervening-row nodes that connect to a later member, leave those two members unstacked or split the stack at the branch layer. The validator reports `[stack-branch-crossing]` because compacting such a stack would reorder and overlap the branch and merge nodes.

Each horizontal stack requires:

- `id`: unique ASCII identifier.
- `members`: at least two node IDs in left-to-right order. A node may belong to only one horizontal stack.
- Members are centered across their original column span and then placed by visible box edges. For each adjacent pair, the generator uses the matching edge's route gap; therefore `shaftLength: "3mm"` remains exactly 3 mm after Arrow 5 midpoint trimming even when wider boxes span the same columns above or below.
- All members share one final Y center. If one member also belongs to a vertical stack, that vertical-stack member is the Y anchor; use this for a source-visible horizontal side branch whose main decision moves during independent-chain compaction.

Each `freeTexts` item requires:

- `t`: exact visible text. Unicode subscripts such as `a₁₁` and LaTeX-like Greek commands such as `\tau` are converted to editable text with character styling.
- `xr`, `yr`: relative anchor position from `0` to `1`, where `xr: 0` is left, `xr: 1` is right, `yr: 0` is top, and `yr: 1` is bottom.

Optional `freeTexts` fields:

- `align`: `left`, `center` (default), or `right`. Left means the text extends rightward from the anchor; right means it extends leftward.
- `vertical`: `true` for stacked editable Chinese labels such as `写入顺序`.
- `italic`: `true` only when the source text itself is italic. Do not infer italics merely because a token is mathematical.
- `subItalic`: `true` only when the source subscript itself is italic; ordinary numeric index subscripts remain upright.

Each `freeLines` item requires:

- `x1`, `y1`, `x2`, `y2`: relative endpoints from `0` to `1`.

Optional `freeLines` fields:

- `arrow`: `none` (default), `start`, `end`, or `both`.
- `lineStyle`: `solid` (default), `dashed`, or `dotted`.

Each `freeDots` item requires:

- `x1`, `y1`, `x2`, `y2`: relative endpoints of the dot row from `0` to `1`.

Optional `freeDots` fields:

- `count`: integer dot count, default renderer value is 18.
- `radius`: positive dot radius in points for Illustrator rendering. The default renderer value is 1.2.

Rules:

- One node occupies one semantic box.
- The renderer rejects visible box overlap and any connector segment that penetrates an unrelated node. Repair topology with rows, columns, stacks, explicit ports, or `via`; never deliver an overlapping layout.
- Include only nodes visible in the source. Never invent `开始`, `结束`, or a grouping frame.
- Nodes sharing a visual rank share the same `row`. Nodes at the same ordinal depth in independent chains do not share a row unless the source visibly aligns them.
- Nodes sharing a visual centerline share the same `column`.
- Center a parent above an even child span with a half-column, for example children `0` and `1`, parent `0.5`.
- Include every visible connection. Repeated `from` values express branches; repeated `to` values express merges.
- If a connector starts from another line, preserve the real topology with `id` + `fromEdge`; do not move the start to the nearest box side. The referenced edge must appear earlier in `edges`.
- If a connector ends on another line, preserve the merge with `id` + `toEdge`; do not redirect it to that line's target node. The referenced edge must appear earlier in `edges`.
- A source node that fans out through one visible bus to three or more targets on the immediately following row uses repeated simple edges with the same `from` and no explicit ports. Three-or-more same-row sources merging into one target use the same omission. This invokes the native comb bus, matching `汇总线.jsx`: each leg is 2 mm, sibling boxes are compacted by visible edges to 1 mm gaps while retaining natural widths, the bus spans the first and last centers only, and its outlet is at the midpoint. Additional feedback or side-return edges from the same source are routed separately and do not disable this adjacent-row subset. A source label on the 2 mm trunk requires `labelSide:"left"` or `"right"`; a target label uses the same side rule at its spoke. It is not a `fromEdge` case.
- Preserve visible source line breaks. For a decision, no rendered line may exceed 14 full-width-equivalent characters. In a dense multi-column flowchart, prefer natural 4–6 full-width-character lines when a longer line would make the diamond substantially wider than adjacent process boxes; preserve a visibly wide source diamond when present.
- Flowchart connections remain orthogonal. Block diagrams and signal-flow diagrams also default to `orthogonal`: preserve source-visible horizontal, vertical, and right-angle geometry. Use `straight` only for a diagonal that is visibly present and necessary in the source.
- For `signalFlow`, use `process` for ordinary straight-corner rectangular blocks, `functionBlock` only for source-visible rounded functional boxes, `multiplier` for the circle-with-× operator, `summer` for the circle-with-+ operator, and `port` for an arrow that visibly leaves or enters the diagram without a terminal box. Put formula/output text on the relevant edge `label`; do not add a fake output box.
- Use `cylinder`, `arrow`, `brace`, `plusCircle`, or `minusCircle` only when that vector primitive is visibly present. Do not approximate a cylinder with `ellipse`, a brace with `freeText`, or an operator circle with a plain `ellipse`; the generator creates the editable path geometry.
- `straight` preserves both declared side centers exactly. An orthogonal opposite-left/right route may project onto the smaller box's centerline when the box heights overlap, producing one horizontal segment.
- `via` requires explicit ports. Consecutive points must share an x or y axis after layout; the Illustrator script preflights and rejects diagonal routes before drawing.
- Prefer `"from"`/`"to"` axes in routes attached to stack members; numeric row lanes belong to the global grid and are not compressed with an independent stack.
- Preserve the source-visible endpoint sides before choosing a route helper. `routeLane` is valid only when both source and target visibly use that same side; a mixed-side return uses explicit `via` points and the outward gap direction table above.
- For a left-to-left or right-to-right feedback route attached to a horizontal-stack member, omit `via`. The automatic same-side route stays exactly 3 mm outside the current box edges and inside the surrounding padded container. A numeric `x` waypoint remains tied to the global grid and will become stale when the horizontal stack is compressed.
- Same-side ports such as `left` to `left` create an outer route one 3 mm lane beyond both boxes. Use this for feedback loops.
- When multiple same-side feedback loops must remain distinct, use `routeLane: 1`, `routeLane: 2`, and so on. Do not use a large numeric `via.x` merely to separate them; that widens the global grid and inflates unrelated containers.
- Reciprocal edges are rejected unless at least one direction uses explicit same-side ports. This prevents the forward edge and feedback edge from collapsing onto the same path.
- Do not include arbitrary style, raw dimensions, or raw point geometry. The generator derives ordinary boxes from current text using calibrated metrics; if text changes, the box changes with it. Use groups, spans, containers, named size classes, ports, port positions, and grid waypoints as semantic constraints.
- Ordinary `process` boxes and borderless `label` nodes use the same deterministic 8 pt character-unit calibration; do not use Illustrator's transient font measurement to widen a grid. `cylinder` is a fixed native storage primitive with a thin top ellipse, straight sides, and curved lower edge.
- Direct orthogonal adjacent boxes have a 3 mm edge-to-edge connector unless their edge explicitly uses `shaftLength:"2mm"`. A native three-or-more-way comb bus uses 2 mm from the source box to the bus plus 2 mm from the bus to the child boxes, so that row gap is 4 mm.
- Decisions containing four or more visible lines use the tall multiline diamond calibration. It grows width and height independently around the text instead of preserving the wide one-line decision aspect ratio.
- A compact merge is different from a branch bus: when same-row sources connect downward to one target on the immediately following row, omit `via`. The automatic `bottom` → `top` routes use one midpoint bus. A `from-gap` plus `to+gap` route reserves 6 mm and must not be used when the adjacent rows do not provide that clearance.
- Container padding participates in row layout. Direct node-to-frame and frame-to-frame connectors terminate on visible boundaries; add `shaftLength: "3mm"` when the selectable shaft, rather than the raw boundary gap, must be exactly 3 mm. Connect to the container ID rather than an internal member.
- A `wideNested` frame keeps its exact 183.5 x 34.4 pt outer bounds. With `bottomRight`, its unlabeled top band follows the same 2 mm container rule and the label uses the remaining lower band rather than forcing the inner box to vertical center. This inset is independent of the 3 mm connector rule.
- The generator owns 0.5 pt strokes, Arrow 5 heads, grayscale, typography, padding, and centering.
- Ellipse nodes automatically receive 20% extra width and height beyond the calibrated rectangular text box so the curved border does not touch the text.

## Released ordinary flowchart shape additions (2026-10-13)

Schema v3 adds `inputOutput` (parallelogram) and `predefinedProcess` (rectangle with two interior vertical bars). Both retain editable text and existing row/column layout, size grouping, ports and arrows. No plugin loader is required.

Dimensions use the existing measured text bounds. `inputOutput` reserves 8 pt extra horizontal space; each bevel is capped at 4 pt, so later equal-height/row-span expansion cannot consume text clearance. `predefinedProcess` reserves two inner bands, each 4 pt at 8 pt font, proportional at 6/7 pt. Outer and interior paths use the existing 0.5 pt stroke.

Left/right ports on `inputOutput` meet its sloping edges. Automatic opposing-port alignment recomputes these boundaries after choosing a common Y. Top/bottom alignment uses the actual horizontal edge overlap. Existing rectangular and other shape measurements are unchanged.

Release evidence: 73 offline assertions and existing validator cases pass. One real 11-node/13-edge flowchart was checked through the pinned Adobe wrapper at 8 pt, including editable text ink centering, arrows and actual PDF. Maximum measured centering offset is 0.000417 pt. 6/7 pt are covered offline only; this is not all-diagram native validation.
