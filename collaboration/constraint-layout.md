# 通用约束版式求解器：隔离开发版

目标：素材与测字数据准备好后，CPU内完成候选位置/版式/避让搜索，输出最终坐标；Adobe执行一次位移或绘制并导出。正式生产尚未接入，当前文件位于feat/pre-draw-layout-20261014工作树，未提交/部署，不启动或占用主线程Adobe。

## 可运行入口

`node collaboration/scripts/run.mjs --config <machine.json> solve <JOB> <INPUT.json>` → layout-solution.json。
`node collaboration/scripts/run.mjs --config <machine.json> solve-batch <JOB> <BATCH.json>` → layout-solutions.json。

批量输入为figures:[{id,scene}]。单图已有两种几何输入：
- tree：复用之前的真实测字框布局输入；标记allowReflow的row/column可自动搜索方向，wrapOptions必须自带对应真实测量且文字内容相同，fontChoices只采用已准备的测量。
- scene：version=1、units=pt、canvas:{widthPt,heightPt}、elements。每项包含id/kind/x/y/widthPt/heightPt；文字附fontSizePt。kind支持text/shape/image/group/plot；固定对象fixed=true，绘图区框geometry=outline，实心对象按包围矩形避让。可给位置candidates、活动region、ownerId与内边距。数据曲线按obstacles.points保留，所属图框通过ownerId声明，线宽参与避让。

硬约束：画布不扩大，字号不降低，fixed对象不移动，文字/图像尺寸不重估，所属框/活动区约束，对齐/先后顺序，文字与矩形/折线碰撞，连接端口方向与箭头头部空间。固定科学曲线只做避让几何，不重画或改数据。未准备的字形测量、复杂路径语义和锁定连线不会被猜成正确。

## 求解方法与“最优”含义

有限域分支限界；同尺寸物体占满彼此分离位置时，自动走最小费用匹配，避免枚举排列。位置候选在源偏好点和障碍边界附近生成，默认最多32个/物体；树版式默认最多64种组合。连接搜索固定端口的正交通道，复用Arrow 5尺寸，默认计算预算50ms。

违规不作为可容忍的低分项。只接受硬约束满足的方案；在其中按移动量、占位面积、路径长度和折弯比较。optimalWithinDomains=true仅表示完整检查了当前有限候选域、或用匹配证明了该域最优，不等于任意连续空间的全局最优。截断候选、超时、缺测量均有显式状态与统计；找到可行解后达到预算，会保留可行解并标记最优性未证。预算是尽力停止的软上限，解析和报告写入不属实时保证。

## 一次执行适配器

collaboration/adobe/solved-layout.jsx定义applySolvedMoves、drawSolvedLayout、executeSolvedExport。数学搜索不在Adobe中发生。位移请求由layout-execution.mjs/buildMoveRequest绑定：原文件SHA、源对象名或集合索引/集合计数、源bounds、可选原文与字体、目标delta与目标bounds。修改源文件或对象时拒绝执行；同对象重复绑定、父子同时位移、既有输出覆盖均拒绝。

scene执行保留原素材，只位移指定对象；重新走线必须提供原shaft/head对象绑定，使用现有JFW.drawArrow5。tree绘制执行固定坐标，只检验一次实际字形尺寸是否与缓存相符。两种路径都保留最终PDF验证。输出保存到独立AI/PDF路径，原稿不覆盖。

已做VM模拟Adobe对象的源校验/一次位移/新图绘制/AI和PDF保存调用测试；**尚未在真实Illustrator中验证这些新适配器，也未挂到正式固定runtime**。主线程需要在副本中做一次原生接入回归，复用现有Adobe互斥、交互恢复、通知和导出审计，不能绕开现行运行版本门禁。绑定源文件并不消除外部并发修改的所有竞态。

## 边界

第一版不是任意图的自动理解器。科学结构、原素材、文字换行许可、可移动范围和真实测量必须在准备阶段明确。曲线输入支持已测量折线；Bezier需准确边界或带误差界的准备结果，不能凭稀疏采样宣称完整避让。实心非矩形暂用保守矩形边界；可以过度阻挡，但不据此改源形状。

连接通道为有限候选，尚未做任意障碍的完备最短路证明、所有连线的联合交叉/共用总线语义求解、字符级任意数学排版重组。图片像素与科学数据没有被这套程序加工。正式生产暂不变，所有限制必须随接入保留。

## 当前验证

日志与30次/场景性能记录：F:/期刊AI工作台/work/side-pre-draw-layout-20261014。合成几何中24标签曲线避让中位0.23ms；10标签位置匹配中位0.12ms；不规则组合场景50ms预算内保留可行解但未证最优；10图批量纯计算约1.64ms。数字不含测字、原生输出、Node冷启动、磁盘/协议准备，不能当整条生产墙钟耗时。执行协议测试是模拟，不是实际Adobe成品证据。
