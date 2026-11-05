# 按类处理、按篇检查：首轮非求解器候选

基线 `ced82c85cb1a8490c52750e772a9415e6ac705f6`。此层读取现有 inventory/production-results，只生成派生报告和候选调度，不建立第二份生产台账。通用求解器由另一 AI 负责，相关几何和 Adobe 文件未改。

**候选代码，不是正式发布。未运行真实 Adobe，未安装、未合并，未触碰作者原稿和验收成品。**

## 组件

- `article-profile.mjs`：按 articleId 归属，用来源/软件证据区分同篇不同生成器；共性仅是观察值，不自动覆盖逐图约束。本版本不新增 Word 解析器，不自动推断字号语义或克隆首图缩放比。
- `case-reuse.mjs`：包装原检索结果。过期、未验收、结构/规范/运行时不兼容或互相冲突的案例不传参数。仅给字体族映射、0.5 pt 描边等有限候选，仍需本图预检和原生检查，不直接复用栏宽、字号或数据。
- `svg_headless.py`：多进程字体族替换，原件不动。支持简单可编辑 SVG；复杂 CSS、tspan/textPath、外链、脚本、转曲文字拒绝。保留路径/坐标/字号/线宽/颜色与文本内容；字体改变后要求重测墨迹。颜色继续走已有 normalize_svg_color.py。
- `measurement-evidence.mjs`：统一 pt、DPI、坐标原点、页号、误差、sourceHash。不是 OCR、语义分割或第二个碰撞求解器；像素证据不能声明为可编辑文字。
- `incremental-plan.mjs`：显式依赖、共享画板和输出hash的失效传播；冻结区域受影响时要求副本；移除节点的旧成品保留。不是实际局部重绘器。
- `queue.mjs` / `native-adapter.mjs`：按图种、路线、格式、规范版本和具体策略排队；保留文章身份；真实执行仍使用原固定入口，Adobe 同机串行。
- `article-readiness.mjs`：核对明确的预期编号集合、终检、缺失、重复、文件hash及声明的同类样式证据。视觉一致性仍需原生审核提供证据。

## 测试

```sh
npm run test:batch
python -m unittest discover -s collaboration/tests -p test_svg_headless.py -v
```

本轮重新执行 107 项 Node 测试与 13 项 Python 测试，均通过。Python 包含真实两个进程的测试；原生适配器采用模拟运行回调和脱敏临时文件，不是 Illustrator/PDF 实测。测试版本和命令见 VALIDATION-20261014.json。原仓库全量回归未在此隔离环境执行。

## 从现有数据生成报告

```sh
node collaboration/scripts/plan-batch.mjs --config <machine.json> --input <batch-evidence.json> --output <新的报告目录>
```

机器配置沿用原 readMachine。读取 recordRoot 中的 inventory.json 和 production-results.json；规范hash来自 knowledge/production-policy.json，runtimeHash来自 RELEASE.json。输出目录必须不存在；不覆盖旧报告。提供历史证据时，入口调用原 refreshIndex/retrieveCases，不信任输入包自称的“当前索引”；过期参数库仍拒绝，不自动更新其可信度。

`batch-evidence.json` 至少含 observations 数组，每项对应真实 inventory 的 id/articleId：

| 字段 | 契约 |
| --- | --- |
| source | `{matched, path, sha256, format}`；真实配对证据，不能靠同篇其他图猜来源 |
| job / plan | job 路径，`plan:{path,sha256}`；相对路径与原入口一致 |
| category / route | 已有图种与加工路线；未知不能入队 |
| strategy | `{fontSizePt,widthMm,colorPolicy}`；字号6—8 pt可小数；原生成器更窄限制仍由原预检把关 |
| decisionHash | `digest(records.figures[id].productionDecision)`；当前试点仅接 confirmed 且无复核冲突的决策，不修改旧决策流程 |
| userConstraints | 明确要求；route/fontSizePt/widthMm/colorPolicy 与方案冲突会阻断 |
| preflight | `{passed,binding}`；实际完成预检后，才用 preflightBinding(item,context) 绑定当前输入 |
| software / observedStyle | 可选软件名、evidenceHash、观察到的样式；缺证据保留未知 |

`preflightBinding` 只计算摘要，不执行预检，也不是授权签名；严禁为了入队批量补 passed:true。`observations` 目前须由既有 ingest/预检 Agent 提供，不宣称已自动从所有原稿提取。

可选 `expected` 生成按篇就绪报告；`measurements` 生成测量接口；`incremental:{nodes,previous}` 生成失效计划；`caseReuse` 配合 `caseEvidence` 生成历史候选。单元测试提供完整可运行的合成数据示例。

## 默认只检查，不调用 Adobe

```sh
node collaboration/scripts/run-batch.mjs --config <machine.json> --plan <batch-plan.json>
```

检查当前台账、源文件、方案、job、规范和发行清单，报告 ready/阻断原因；不制作。它不是原生验证结果。

只有完成本机交接、确认唯一写入者并通过副本测试后，才执行：

```sh
node collaboration/scripts/run-batch.mjs --config <machine.json> --plan <batch-plan.json> --apply --single-writer-ack --report-dir <新的运行目录>
```

single-writer-ack 是操作人已核实交接的确认，不是自动校验回执。批次使用排他锁，各项仍经原 collaboration/scripts/run.mjs 执行；保留其 runtime 文件校验、原生锁和版本事件。不自行重启软件、杀进程或清除未知旧锁。

每项前置复查实时权威状态；台账或版本变化停止本批。纯单项前置错误隔离；原生失败无法证明宿主健康时停止 Adobe 队列。返回 0 后仍核对实际保存方案、原生记录和 output/ai/preview 字节hash；旧字体或文字的结果不能借同一 sourceHash 通过。若旧渲染缓存未更新 job 的结果引用，会保守阻断，需原生产线程核对，不自动重绑验收。

追加 `--previous <旧result.json>` 时，只重用输入一致且再次验证记录、方案及输出文件的成功项。耗时和事件记录在新目录；渲染完成不等于用户验收，不写 userAcceptance。

## SVG 并发预处理

```sh
python collaboration/batch/svg_headless.py <svg-jobs.json> <缓存目录> --workers 2
```

清单是数组：每项含 id/source/sourceHash/fontFamilyMap。source 相对清单目录解释。默认2个进程，可1—8，不按CPU核心数擅自全开。输出为 prepared-for-native-review，不是成品。内容寻址缓存仍重新验证变换结果；缓存文件和manifest一起被改也不能自证通过。异常副本保留，不覆盖原件；无生产提速百分比结论。

## 按篇交付门禁

```sh
node collaboration/scripts/sync-delivery.mjs --config <machine.json> --require-complete <expected.json>
```

不带新参数保留原入口行为。expected 数组逐图指定 id/articleId/numbers/decisionHash，必须覆盖当前 inventory；不能根据“没识别出子图字母”默认整图。严格门禁要求明确 userAcceptance.accepted=true 与真实输出hash；旧文字状态不单独满足新门禁，不能批量补 true 绕过。

任意文章不齐套则先报错，原交付器不执行。全部满足才调用原 syncCurrentDelivery。**本版是全批阻断，不是按就绪文章单独增量发布。** 报告会分别指出哪些篇就绪，但不擅自筛掉未齐套文章并撤回其旧排版外链；更细发布策略仍待现场集成。

可声明 consistencyGroup/styleHash/explicitStyleException，必须来自当前成品审核证据；程序不把这几个字段冒充自动视觉测量。

## 与另一 AI 及原生产线程的接续边界

求解器接口为 pt、左上原点、boundsPt{x,y,width,height}，同时提供 sourceHash/engineVersion/uncertaintyPt/clipped/semanticCompleteness。是否需要原生重测由求解器判定。字体变更后旧墨迹证据应失效；接口尚需双方确认，不修改对方实现。

增量 inputHash 必须包含实际影响输出的源、方案、测量、规范和工具；dependencies 显式提供，共享画板声明 sharedGroup。该层不凭图种猜依赖。

尚未完成：本机唯一交接、既有P0验收绑定风险收口、Windows/Adobe/PDF副本验证、真实墙钟基准、工作台入口、全部结构化证据自动提取、反馈核准UI、按篇独立增量发布。此候选不解决既有 Windows PID/recovery 回归，也不修改 RELEASE 或安装 Skill。源码包不是完整仓库，不要直接覆盖并行 AI 的工作树；使用独立分支/PR集成。
