# 制作说明：不是每张图另写脚本

制作说明JSON是可再生成母版；原始素材保持只读。新增图件由Agent先读原稿、核对内容和连接，再选现成模板填说明。不要把这些模板当成自动识图系统。

## 公共字段

`version: 1`、唯一`id`、`author`、`kind`、`policy`和`sources`。真实素材的`sources`应含相对文件路径、SHA-256及`source/reference`角色。合成测试须明确`synthetic: true`；不能借此规避真实稿件来源绑定。

`policy.column`为single/double/auto。以8 pt为优先起排字号，允许按版面实测使用小数字号；不低于6 pt，低于6 pt必须重新排布。改变文字或字体后会重新测量；完成布局后整图等比适配，允许小数字号；低于6pt必须重新布局，最终可见矢量描边恢复为0.5pt。文字可以是字符串，或`[{"text":"K","style":"italic"},{"text":"=50"}]`样式片段。

## 图形模板

- tree：root、branches[{text,children}]，可选root_vertical。
- cycle：四个stages[{title,items}]、decision、end、reject_labels。模板顺序为左上→右上→右下→左下→判定，两条回路分别回到阶段1/2。
- layered：stages、support、down_labels、return_label，支持左侧总支撑及右侧反馈回路。
- radial：corners、core、ring_top、ring_bottom、cycle_labels。角节点按左上、右上、右下、左下排列。
- fanout：top、items、bottom，分发与双向数据连接。
- network：节点中心/半径、edges[{from,to,arrow,both,via}]；坐标由Agent/外部布局提供。
- scene：节点、文字、带端口的连接和折线路径；用于模板之外的规则图，但不宣称自动求解任意坐标。

## 统计图

`source_kind`为svg/raster/pdf。使用原图的`plot_clip`、`x_ticks/y_ticks`中的`position/text`进行坐标位置绑定，不从像素反推数据。`plot_width_pt`为最终绘图区宽度。`series`用稳定id绑定label、源曲线组和样符组/裁取区。SVG支持已识别的Matplotlib分组；一般PDF版位能保留，但不保证任意PDF能够自动删除旧文字。

位图清字须显式`masks`和`approved_empty_regions`，图例仅允许已审核`legend_safe_region`。这些安全区域是读图审核输入，不能填写不存在的空白证明。SVG图例可用原路径位置做避让，未提供或不确定的曲线不能被宣称已完整保护。

源码包的examples/含无真实作者资料的树图、网络和混排示例；完整试用包private-samples/specs/含本次真实图件说明。复制参考必须同时核对原图语义与来源。
