# 通用图形配置与复用

普通流程/框图只提供文字、节点形状、连接和布局约束；不在作者脚本中画SVG路径或调用Illustrator逐个画框。以 `collaboration/fixtures/common-shapes.flowchart.json` 为非作者示例，通过正式 `run.mjs render` 调用随版本固定的生成器。

| 需求 | 通用配置 |
|---|---|
| 椭圆 | `shape: ellipse`，真实文字确定大小，保留文字墨迹居中 |
| 单向粗箭头 | `shape: arrow`，`arrowDirection: left/right/up/down` |
| 双向粗箭头 | `shape: arrow`，`arrowHeads: both`；与普通双向连接线区分 |
| 输入输出平行四边形 | `shape: inputOutput` |
| 预定义过程双竖线框 | `shape: predefinedProcess` |
| 判断菱形 | `shape: decision`；正式适配复用文字加菱形框的0.85/0.8与2pt留量，再检查文字角部净距 |
| 同列普通矩形等宽 | 同一语义列使用相同 `widthGroup`；不要把菱形、照片和所有不同列强制等宽 |
| 外框标题 | 容器标题参与测量；先预留标题高度及净距，再确定外框和相邻行间距，最后布线 |

双向粗箭头在8pt时基本长度24pt，标签较长时同步留宽；长度随字号缩放。箭头标签独立可编辑，并参与行间空间计算。箭头方向、单双头、大括号方向须穿过布局阶段保留，不能只在输入验证阶段存在。

存在唯一自上方进入容器成员的同列竖直连线时，标题按该连线定位：文字真实墨迹左缘距0.5pt线条右缘固定3pt；不跟随外框宽度靠右漂移。标题宽高先测量，外框据此包围。多入口情况不猜测唯一锚点。复杂多条入线仍需检查实际PDF；标题留量通过不表示所有连线碰撞已解决。实际源为照片组合、存储分区或时序时保留其语义，不强行当成普通流程图。未实现的图种记为待迁移，不将手写SVG包装成通用生成器已完成。

### Semantic technical layouts (r12 candidate)
The same `rebuild` entry accepts schema 3 `kind: technical` with `layout: memoryMap`, `sequence`, or `photoComparison`. Author plans hold source labels, ordered protocol messages, normalized memory boundaries, or image paths with SHA-256. Illustrator geometry remains in `flowchart/assets/technical-layouts.jsx`, using existing measured text, boxes, lines, and image embedding. Comparison columns and section heights are measured as groups; sequence response/request rows reserve independent ink space. A width overflow fails explicitly rather than silently shrinking text. Current sequence layout supports exactly three participants; photo comparison supports two or three columns. Source image bytes participate in render identity and are checked before cache reuse.
