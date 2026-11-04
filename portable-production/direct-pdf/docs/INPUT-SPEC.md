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
  `texts`可声明`fit`把标签排版交回工具：`{"width_pt":44,"max_lines":2,"allow_angles":[0]}`，
  工具按「单行横排→按分隔符拆行仍横排→倾斜兜底」的顺序实测决策，任何一步都不缩字号；
  决策写入`layout_evidence.label_fit`（含`reason`、实测宽与可用宽）。`anchor`可取center/top/bottom，
  用于按字块边而不是中心定位。放不下时抛`label_does_not_fit`并交回实测宽度，要求改版面。

scene 重绘时，不要把同组框的间距留给手写坐标。`measured_groups` 的默认墨迹框距为 3 pt（8 pt 字号时）；`measured_node_groups` 指定 `grid_columns` 后，无连接节点默认按文字测量并自动排列，末行可以不满。已有连接的节点不会自动挪动，间距仍由检查器核验；需要改线时须提供明确可联动的布局，不能只移动框。

未显式分组的普通文字矩形在横向或纵向投影相邻时，生成阶段优先自动达到 3 pt 墨迹净距（随字号按规范缩放），同步移动框内文字及可安全联动的正交连接端点。涉及资产、无法安全移动或需要复杂绕线时不猜测，检查未通过则返回需要重新排布；直接连接的框按连接规则处理。此能力不推断语义分组，也不自动完成整图紧凑排版。

两条竖直反向箭头连接一个容器底边与一个独立框顶边时，可声明 `"compact_links": [{"anchor":"容器ID", "target":"独立框ID", "paths":["向上箭头ID", "向下箭头ID"]}]`。在容器完成紧凑排布后，公共工具同步移动独立框、文字和两条线；方向、边界端点和 3 mm 箭头保持。目标有其他连接或新位置碰撞时会报错，不自动猜测。该入口只处理此类明确拓扑，不会自动识别所有场景的语义组或任意绕线；未声明的容器与连接仍要在方案中按实际图意安排。

同一行中无需连线的相邻容器，可在各自 `compact_containers` 声明成员后设置 `"compact_container_rows":[{"containers":["左组ID","右组ID"]}]`；工具按 6 pt 墨迹组距移动右侧容器、内部框和标题。右组或其成员带连接线时会拦截，不能仅移动外框。

相同层级需等宽的分层区域，可声明 `"equal_width_container_bands":[{"bands":[["上层ID"],["中层ID"],["左下ID","右下ID"]],"titles":["总标题ID"]}]`；每个数组是一层，取各层最大实际跨度统一左右边界，底部并列组保留既定组距，内容随容器居中；声明的总标题也随等宽层整体居中。成员连接必须已由支持联动的入口处理，不能通过扩框改变拓扑。语义关系由来源确定，不能把互不对应的容器强行等宽。

对于已用 `compact_containers` 与 `compact_container_rows` 明确划分并列组、其余层上下排列且左边界对齐的结构，省略 `equal_width_container_bands` 时公共入口自动补齐各层等宽；上方只有一个独立文字时一并居中。边界不一致、层叠或存在多个可能的标题时返回 `container_bands_ambiguous`，由方案明确语义。没有并列组声明或不是这种简单分层结构的图，不会据外观擅自推断。

## 统计图

`source_kind`为svg/raster/pdf。使用原图的`plot_clip`、`x_ticks/y_ticks`中的`position/text`进行坐标位置绑定，不从像素反推数据。`plot_width_pt`为最终绘图区宽度。`series`用稳定id绑定label、源曲线组和样符组/裁取区。SVG支持已识别的Matplotlib分组；一般PDF版位能保留，但不保证任意PDF能够自动删除旧文字。

位图清字须显式`masks`和`approved_empty_regions`，图例仅允许已审核`legend_safe_region`。这些安全区域是读图审核输入，不能填写不存在的空白证明。SVG图例可用原路径位置做避让，未提供或不确定的曲线不能被宣称已完整保护。

源码包的examples/含无真实作者资料的树图、网络和混排示例；完整试用包private-samples/specs/含本次真实图件说明。复制参考必须同时核对原图语义与来源。

### scene 词组、直线连接与分区收紧

使用 `wrap_chars` 的中文无空格标签由系统 ICU 词边界分行；常见“采集电路”等复合词尽量保持完整，型号保持原文。分词并非语义证明；图意有歧义时应提供明确换行。

`straighten_connections: true` 在端口可安全重合时自动将未共享的普通框连接改直线；原方向、箭头、两端归属不变，并经碰撞审计。`align_connections` 可声明 path、source、target 和可选 source_fraction，生成器联动移动目标及其连接，再验证。`compact_container_bottoms: true` 在边界无连接绑定时按框、文字和穿越连线的实际范围收紧分区下缘。以上均不适用于内嵌资产，不能承诺处理任意拓扑或全局最优排版；有碰撞或需复杂绕线时明确报错。
