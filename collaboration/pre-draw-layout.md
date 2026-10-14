# 绘制前统一布局计算（隔离开发版）

入口：`node collaboration/scripts/run.mjs --config <machine.json> layout <JOB> <INPUT.json>`。
另可单独用 `node collaboration/scripts/pre-draw-layout.mjs INPUT.json REPORT.json`。计算纯数学，不调用Adobe，不写正式台账、不修改输入。输出JOB/layout-calculation.json和版本事件，退出0为ready/exempt，2为待测量/需重排/冲突，1为输入错误。

## 计算顺序

真实文字墨迹 → 内框 → 等宽/等高组 → 嵌套外框 → 端点及箭头标签 → 整图适配 → 碰撞检查。

规范直接读取已有production-runtime/adobe/editorial-layout.jsx，不另建一套4.5/2.7 pt与3 mm常数。普通矩形按文字加左右4.5 pt、上下2.7 pt；菱形/椭圆按文字保护矩形角点计算可容纳边界。同组最大尺寸先传播，再定位。无连线默认3 pt；相邻明确连接默认3 mm基础箭头长度，两端贴框。显式gapPt可加大，过短连接会报冲突。

输出nodes/texts/frames/edges坐标为pt，x向右、y向下，均是整图等比适配之前的坐标；最终变换为 `(坐标+fit.translatePt)*fit.scale`，所有元素一同适配。最小字体乘scale低于6 pt时needs-reflow，保留原目标栏宽，不自动升级双栏。连接标签由指定线段、方向、gapPt计算，标签占位也进入整图容量。

## 输入与测量真实性

version=1，font/fontSizePt/widthMm，tree，measurements，edges。tree支持box、row、column、frame；box支持rectangle/diamond/ellipse。box的id对应measurements键；frame标题使用frame.id；箭头标签使用`edge:<edge.id>`。测量必须包含原文字、真实字体、同一字号、widthPt/heightPt；有字符样式时传styleFingerprint，必须与输入匹配。节点可指定widthGroup/heightGroup。

测量数据由已有Illustrator测字/临时轮廓工具取得，计算器不估字宽。文字、字体、字号或样式不匹配即needs-measurement。新增独立math命令使准备人员在画整图之前拿到坐标与冲突证据；不把绘制后碰撞检查冒充绘制前计算。

示例collaboration/pre-draw-layout-example.json是合成数学夹具，不是实测字体证据；正式使用必须替换为真实测量记录。该版调用者应保留测量来源和哈希；此模块校验测量身份和数值，不自行证明上游测字是否真实。

## 首版范围与接入边界

支持显式嵌套框布局、分组尺寸、正交连接、沿连接的固定距离标签、整体容量和几何冲突。复用lib/diagram-audit.mjs检查文字与路径碰撞。对没有layout输入的非PS路线返回needs-measurement；PS image明确exempt。未实现任意复杂图的自动改拓扑/自动绕障，不猜连线或原图结构。

本分支没有修改生产runtime清单、安装Skill或主线程工作台。原render入口行为保持现状；layout命令是统一准备入口，还不是默认强制生产门禁。计算坐标如何送给各既有绘制渠道，需要按渠道适配并做原生副本验证；在此之前不能宣称模型坐标已经被实际Illustrator成图采用。ready只代表给定测量与布局的数学可行性，最终PDF、原图拓扑和专业内容仍必须检查。

验证覆盖缺/旧测量、字号下限、等宽/等高、菱形/椭圆容字、3mm贴框箭头、标签固定间距、标签进入容量、穿框冲突，及CLI不启动Adobe。隔离分支feat/pre-draw-layout-20261014，未提交/上线。
