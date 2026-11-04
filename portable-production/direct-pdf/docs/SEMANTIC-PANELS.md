# 从语义分组生成版面

`semantic_panels.measure_panel/place_panel` 复用 FontRegistry、label_layout 和 region_layout，根据内容及行列关系计算全部框、标签和嵌套分区尺寸。普通框用公共墨迹留白；`gap_pt` 明确框距3pt、组距6pt，连接通道另计。`place_panel` 的原点仅是整图留白，不是逐对象坐标。

叶节点：`{id,text,box,vertical,wrap_width_pt}`。组合：`{axis,children,frame,title,padding_pt,gap_pt,dash,align,equal_width}`。`stretch_last` 只拉伸已明确为区域的末项，子内容保持居中；不会把普通框随意加宽。来源确实锁定的宽条形框可用已有 `source-locked-viewport` 来源证据，生成器须保留其role供检查。

结果包含 nodes、texts、真实宽高及测量evidence，继续交给现有scene/统一runner执行。任意拓扑的连接语义、源图标裁区和重叠关系仍须从来源绑定；不能根据外观猜测，不能把对象的空间相邻自动当成连线。

字体支持任意有限角度；position_text、PDF绘制和碰撞检查共用旋转后的文字几何。斜字碰线判断用实际文字区域，避免水平外包框误报；真实交叉仍拦截。

`rebuild_fidelity` 在生成前执行来源绑定的样式/栏宽约束，在生成后检查层级。白框约束去掉灰填充但保留必要的不透明白填充，避免重叠源圆的背面线条穿字。来源节点、独立连接及原图标不能由allowedChanges自行改写。

真实使用及回执：本地工作记录 outputs/side-wei-feedback-20261104；卫冠杰1–4本轮从来源重新制作并回传待终检，其中图2–4单栏，实际PDF文字均为8pt。它们仍需用户终审，不能收录为已终审成功案例。
