# 2026-10-12 工具同步与接收入口

本次主线是制作前判断、批量审核、渠道分配和减少返工。此任务分支保存当日完整代码与规范，不等于所有候选已经成为正式生产能力。

## 版本与边界

- 正式 runtime 仍固定为 `2026.10.12-r2`，由外部 machine.json 配置；未重装 Skill、未替换 RELEASE.json。
- 根目录研发源码、协作 run 入口、正式 production-runtime 有明确差异，禁止整树互覆。
- GitHub 管代码、规范、合成测试；真实 Word、AI/PDF、截图、权威台账及机器配置从独立交接包取得。
- 办公室生产及 Luna 判断均已暂停。接收机校验、核并并回执后成为唯一生产者。

## 本日变更索引

| 领域 | 实现和接手入口 | 当前边界 |
| --- | --- | --- |
| 制作前审核 | workbench/decision-board.js、decision-review.js、source-review.js | 固定主标题及三个导航；按作者对照图源；批次筛选；原位缩放平移；属性拖拽 |
| 拆分与分流 | workbench/decision-attributes.mjs、routing-tasks.test.mjs | 拆分采用原图→交付方案及备注；渠道任务是准备清单，不是执行许可 |
| 状态保护 | workbench/decision-store.mjs、source-review-store.mjs | 保存原AI建议、人工改动、历史与revision；用户草稿也保留；不改生产验收 |
| 已通过案例检索 | knowledge/README.md、decision-retrieval.mjs、collaboration/scripts/prepare-decisions.mjs | 新判断前实际检索；只复用有证据的路线/结构事实；无匹配不强套 |
| 模型判断边界 | knowledge/decision-boundary.mjs及测试/说明 | 本地硬约束、原始子图题与视觉区域分离、路线与栏宽解耦；候选不自动发布 |
| 跨月素材搜索 | collaboration/scripts/find-prior-artwork.mjs | 一次遍历生成候选；仍须核对最新Word、文章身份及实物 |
| 原生执行前预检 | collaboration/scripts/run.mjs、plan-preflight.mjs | 合同预检、调用ID、方案hash、耗时日志；不是完整布局求解器 |
| Visio SVG准备 | lib/convert.mjs、scripts/convert-office.js、prepare_visio_svg.py、collaboration/scripts/prepare-visio.mjs | 显式选页、缓存及线身准备；保留默认PDF路线；仍需检查文字和渐变退化 |

## 当前业务契约，覆盖设计文档中的旧试验方案

1. 主导航固定为当月生产、图件分类、生产与提速；不改编辑/作者主页。
2. 图源匹配→拆分数量→加工方式→栏宽。匹配采用Word完整主图与全部附件对照，支持批量确认、备注和粘贴截图；证据不足不自动通过。
3. 拆分不使用看板、不放进图源匹配；有子图/确需拆分者用原图→交付方案；交付方案管理其各输出栏宽，不再进入常规栏宽板。加工方式正常审核。
4. 栏宽与加工方式批量拖放，原始AI与人工变化均保存。原始子图题、视觉区域、实际交付集合分别记录，不编写作者未提供的a/b标记。
5. 图种标签不能决定审计放行。PS图片大致匹配并走常规输出检查，不进行细致内容专项或准备连线表。混合重绘允许保留原像素素材。
6. 加工路线和容量证据分离：已有明确人工栏宽优先；未知标待实排，制作时复用现有fit/墨迹/净距检查。不能为预判启动多轮Adobe试排。
7. 低于6pt不得自动放行。外部生成器有自身支持范围，不能将其限制推广到原生parallel-chains等所有路线。
8. 内容疑点保留原文并交编辑/作者；方案确认不改变生产或终检。修订只重新核相关依赖，不扩成全稿版本监测系统。

## 不得误认为已经解决

DeepSeek/Jev新样本曾错拆分及违背明确要求，未达默认采用门槛；接口费用低和响应快不等于全流程提速，不强制每图调用Jev。旧盲测样本已冻结作回归，后续人工改判优先于实验参考答案。
Visio SVG真实副本能保住箭杆，但文字重叠/渐变尚未通用解决。全重绘有足够Word证据时跳过无用SVG准备。过线桥、密集电路文字归属/修订范围、旧预览缺失根因仍需新图覆盖。
几何比较候选仅限定范围留档；图像审计存在混合图误拒，禁止全局替换。预检能拒绝不支持参数，但不能宣称版面全部可行。

## 验证及后续

本次同步前64项相关回归通过：

```text
node --test workbench/decision-store.test.mjs workbench/routing-tasks.test.mjs knowledge/decision-boundary.test.mjs knowledge/decision-retrieval.test.mjs collaboration/tests/entrypoints.test.mjs collaboration/tests/plan-preflight.test.mjs tests/visio-export.test.mjs tests/visio-svg-preparation.test.mjs
```

这是隔离静态/文件测试，不是所有图种Adobe回归，也不改正式成品。此前真实生产计时与失败样例随交接资料保存；不同复杂度批次不能用于宣称普遍提速比例。首要指标仍是素材就绪至可审核/可终检总墙钟、返工轮数和人工介入，而非单函数或单API时间。

接收时先核对此分支、外部路径和资料包，保留本机新反馈，不能整份覆盖台账。最新用户终检/修订以资料包正式记录为准。Luna（Medium）首3张仅为检索中间稿，未完成接入门槛；先纠正人工栏宽草稿保护和子图泛化，再验证几张，主Agent统一发布后才能逐批扩大。子代理不直接写生产权威记录。
