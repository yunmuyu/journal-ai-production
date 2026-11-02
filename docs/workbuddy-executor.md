# WorkBuddy 制作接入

当前试验分工：工作台登记、派单、显示日志与待终审稿；WorkBuddy 调用现有公共作图工具；Codex 修复公共工具问题。文章 ID 用于身份与回传归档，队列按已核对图种和加工方式领取，不能按篇连续制作。

## 可移交产品目标

目标是“兼容执行 Agent＋GitHub 工具＋资源＋用户少量关键决策”。WorkBuddy 是无长期开发上下文的测试执行员，不是永久供应商依赖；当前 ChatGPT 协调与救场是开发阶段安排，不是最终产品必须经过的人工关卡。“兼容”要求实现领取、续租、日志、暂停、失败和产物回传协议，并具备相应读图及工具能力，不承诺所有 Agent 无需适配。

来源约束、制作规则、状态、反馈和版本关系应由公开工具与仓库外持久记录承载。更换执行器应复用任务及进度，不复制业务逻辑或重建生产状态。先稳定当前真实链路，不以这一目标为由替换框架或另建平台。公共缺陷修复须留下通用规则、诊断和回归测试。

常规制作、自检、普通反馈修订和可恢复失败逐步由兼容执行器与工具闭环；真正缺资料、语义冲突和重要取舍才给用户证据、建议与最小问题。用户最终批准始终保留。当前已验证的持久派单、日志、来源校验和回传不依赖聊天记忆；语义判断依赖执行 Agent 能力，终审分流和复杂工具故障仍需活动协调会话。没有验证过的自主闭环不能称为已实现。

按加工路线从现有日志记录首次送终审比例、人工/协调者介入次数及原因、用户耗时、普通修订闭环情况、来源或语义错误、重复任务与错版本事件。先有实测再逐类减少介入；不把探索性的图件数量当成熟门槛或工期承诺。机械检查、视觉/语义核验与用户批准分别记录。

## 按处理路线调用公共工具

先核对原包、Word当前可见图和候选源件，确认是否存在更适合的可编辑或矢量来源；处理路线不能只由PNG/JPG后缀决定。常规照片、截图，以及已明确输入顺序和布局的组合位图，用 [公共raster入口](../portable-production/raster/README.md) 的 `python -m raster render <plan.json>`，保留内容并处理灰度、显式裁切、尺寸，交付JPG。该路线不依赖Photoshop，任意满足执行协议和依赖条件的Agent均可调用同一工具；必要特殊格式才使用已有Adobe兼容入口。

重绘/可编辑文字路线使用相应PDF工具及字号审计。位图内不以像素字高估算字号，不据此触发重绘、拆屏、双栏或用户追加审批；同时必须检查内容缺失、关键文字可辨和灰度后含义是否仍完整。不得把重绘要求拼入截图任务，也不能以JPG不查字号为由免除独立质量检查。

派单前按持久路线契约检查来源、操作范围、格式和检查项是否一致；回传后由公共 `task_quality` 重读实际产物、重生成预览，并由独立审阅记录内容、可读性和灰度语义。执行者完成报告只是输入证据，候选回到工作台待用户终审，不自动批准或覆盖已批准交付。

公共raster的单图及多输入组合CLI有合成照片/界面夹具测试；实际作者多输入组合在工作台端到端回传尚须另行记录验证，不能用合成通过代替。当前源码可调用不等于旧Release安装包已经包含该入口，具体发布范围以新Release及其清单核验为准。

## 当前边界

这是本机执行会话主动领取的接口，不是 WorkBuddy 桌面应用的远程启动接口。需要在 WorkBuddy 启动一次执行会话。会话退出后，工作台重试只能重新排队，不能凭空启动 AI；页面必须如实显示等待领取。不得使用未授权的私有 IPC 或读取登录票据来绕过这个限制。

试跑完成回传后，才能启动本批来源核对和图种分组。分组清单须覆盖本批每篇文章，无法读取、缺图源和不确定语义须明确报告，不能视为无图。核对阶段不是按篇制作；核对完成后按逐图任务的 `group` 排序，跨作者同类处理。已完成试跑不重复派单。

## 部署契约

现有工作台服务导入 `workbench/workbuddy-http.mjs`，调用 `createWorkBuddyHandler({root,origin,config,publish,restore})`。在已有 Host 检查后、普通静态路由前调用返回的 `handle(req,res,url)`。`root` 为仓库外持久任务目录。`publish` 将已校验产物接入当前模型；`restore` 恢复已回传任务。现有修订回放在此后运行，避免旧制作稿覆盖新修订稿。

`workbench/workbuddy-candidates.mjs` 提供现有文章/图件数组的候选激活适配器。接入时必须保留批注及原验收记录，新输出标为待终审，其他未完成图件标为待制作，不自动计算为已通过。

前端在 `#toolbar` 后加载 `workbuddy-ui.js`，复用工作台 Tabler 样式。服务提供同名静态 JS 入口。公开代码不包含本机路径、原稿、运行认证配置及候选图。

仓库外 `config` 包含：

- `workerToken`：本机生成的随机凭据，只供执行器回调；禁止放入浏览器或 Git。
- `reviewerToken`：独立内部审阅入口的独立凭据，不发给执行器、不放入浏览器或Git；执行者token不能调用审阅接口。
- `qualityPython`：服务端独立运行 `python -m task_quality verify` 的已验证Python绝对路径，须具备公共质量门依赖；未配置时不能激活制作候选。
- `pilot`：`key,label,group,articleId,figureNumber,mainNumbers,outputNumbers,sources,productionRoute`。sources 每项为只读文件 `path,sha256`；instructions须按productionRoute生成，不能沿用通用PDF/字号模板。
- `catalog`：`batchHash,articles,archive,groups,completedKeys`。articles 每项为 `id,author,title,word:{path,sha256}`；旧非空 `productionInstructions` 会被拦截，迁移为逐图productionRoute。
- `inventory`：来源核对任务，`kind:"inventory"`，包含唯一 key、label、group、sources 和核对指令。

部署时使用 `workbench/workbuddy-skill/SKILL.md`，旁边的本机 `connection.md` 提供RUNNER、CONFIG、仓库、Python、字体profile路径。执行器CONFIG包含 `origin,workerToken,session,engineRoot,toolsRoot`，不提交Git，也不包含reviewerToken。`engineRoot` 指向已验证的公共 `portable-production/direct-pdf`；`toolsRoot` 指向公共 `portable-production`。CLI的run注入PYTHONPATH，分别调用 `-m journal_pdf`、`-m raster`、`-m task_quality`。运行前核实对应模块的 `__file__`，不复制引擎覆盖运行环境。仓库技能改动不代表已安装技能同步或正式Release已发布；部署与真实调用须另留验证记录。

## 终审意见分流

保存批注仅保存反馈；点击“提交终审意见”后进入 ChatGPT 待分流，不自动启动另一个 Codex 制作进程。普通修改交给 WorkBuddy；公共工具问题先修复并记录提交和测试证据，再派优先修订任务。执行失败返回协调者排障，通用重试按钮和接口不能绕过分流。

接入 `createReviewTriage`（`workbench/review-triage.mjs`），配置仓库外 `root`、同源 `origin`、私有 `token`、WorkBuddy `queue`、文章和图件模型，以及 `refresh/activate` 适配器。处理器排在旧 `/revision-jobs` 路由前；旧 `createRevisionHandler` 设置 `enabled:false`，仅保留历史回放。先回放普通制作稿，再回放旧修订，最后回放 WorkBuddy 修订；`decorate()` 在旧修订装饰之后执行。

协调者通过 Bearer 认证的 `/review-triage/resolve` 提交 `id,decision`。decision 包含 `kind:ordinary|tool_fix|mixed` 与明确 `instructions`；工具修复另需 `toolResolved,toolCommit,tests`。中断任务只有核实原执行停止后才传 `confirmedStopped:true`。修订绑定稿件图号、批注修订号及基稿版本；期间新批注或新稿出现时，旧结果拒绝覆盖。回传保留原反馈和版本，仍待用户确认。

分流记录持久化不等于自动唤醒 ChatGPT；协调者需要在活动会话读取并处理。WorkBuddy 同样依赖已启动且继续领取任务的会话，页面排队状态不得冒称后台 AI 已启动。

## 可观察的操作

浏览器操作使用同源校验；执行器 `/workbuddy/worker` 回调必须携带 Bearer 凭据。CLI 入口 `node workbench/workbuddy-cli.mjs <配置> <操作>`：

| 操作 | 行为 |
|---|---|
| `claim 60` | 最多等待 60 秒领取；未领取不能声称执行中 |
| `progress <lease.json> <文字>` | 回传阶段和具体进度 |
| `run <lease.json> <程序> <参数…>` | 记录命令、退出码及输出，运行中每 15 秒心跳 |
| `heartbeat <lease.json>` | 阅读或分析期间续接并检查暂停 |
| `paused <lease.json>` | 保存后确认安全暂停 |
| `fail <lease.json> <错误及证据>` | 记录失败，保留本次产物，交给 Codex 排障 |
| `submit-candidate <lease.json> <result.json>` | 制作／修订任务提交候选，解除执行租约，进入review_pending；不激活终审稿 |
| `complete <lease.json> <result.json>` | 仅inventory来源核对任务；校验全批清单后生成按路线派单，制作任务调用会被拒绝 |

暂停不会强杀 Adobe。继续或失败重试生成新 attempt 目录，保留旧日志和候选。两分钟无心跳只代表待核实，原租约可续接；不能据此断言原进程死亡或启动重复制作。工作台重启同样保留原租约。明确确认旧执行已停止后，才允许对中断任务重新排队。

成图结果结构见执行器技能。独立审阅者取得源件、候选和公共quality合同，执行postcheck并查看工具从实际文件重建的预览，逐项填写独立review回执后执行finalize/verify。审阅者与producer不同；执行者不代填独立回执。审阅者用reviewerToken向 `POST /workbuddy/review-candidate` 提交 `{"id":"<job-id>","result":<reviewed-result>}`；result保留已提交候选的图号、路径、SHA256，补全 `quality.contract:{path,sha256}`。服务重新运行公共verify后才接入待用户终审。不能在审阅时换文件；修改须退回并新建attempt。

不通过则向同一接口提交 `{"id":"<job-id>","decision":"rejected","reason":"具体证据与修订要求"}`，保留候选、日志和退回记录，任务进入needs_input；修复/重新排队在新attempt中处理。上述审阅接口不是worker CLI的review/reject命令。执行器没有审阅token，不得自审放行。

分组结果为 `evidence,articles`；每篇含 `articleId,evidence,figures`，每张可制作图须含 `number,group,outputNumbers,evidence,productionRoute`。productionRoute版本1包含 `method:raster-preserve|editable-pdf`、sourceReview和requirements。sourceReview的archive/word/inventory/selected为路径及SHA256引用，candidates逐项含path/sha256/kind（raster/vector/editable）/decision（selected/not-applicable）/reason，并填写basis；位图路线另填rasterReason。组合按selected后接additionalSelected的顺序登记全部选中源，必须与candidates一致。requirements只含format/fontCheck/widthMm：位图为jpg/none，重绘为pdf/editable，宽度为已核对值。原包、Word和源件逐项验证，不以扩展名自动选路线。

多源位图每任务一个组合输出，公共raster计划纳入quality合同source_inputs冻结；回传 `quality.rasterPlan:{path,sha256}`，计划输入及顺序、布局、输出路径和宽度须匹配任务。阻塞图附blocked:true/problem；整篇阻塞figures为空。确认确实无图须附noFiguresConfirmed:true。保存、内部审阅与机械检查均不代表用户验收，整批放行仍须用户明确“全过了”。

## 验证

`node --test workbench/*.test.mjs` 验证队列、来源变更、路线合同、身份、暂停恢复、心跳重连、HTTP授权、CLI日志和候选/独立审阅回传。HTTP测试使用传输夹具，不是实际制图验收。真实接入还须用WorkBuddy执行图件、独立核对源件和最终PDF/JPG、通过独立审阅接口回传，并在浏览器确认待终审预览；不能用单元测试代替。
