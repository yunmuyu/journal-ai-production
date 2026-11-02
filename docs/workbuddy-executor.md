# WorkBuddy 制作接入

分工：工作台登记、派单、显示日志与待终审稿；WorkBuddy 调用现有公共作图工具；Codex 修复公共工具问题。文章 ID 用于身份与回传归档，队列按已核对图种和加工方式领取，不能按篇连续制作。

## 当前边界

这是本机执行会话主动领取的接口，不是 WorkBuddy 桌面应用的远程启动接口。需要在 WorkBuddy 启动一次执行会话。会话退出后，工作台重试只能重新排队，不能凭空启动 AI；页面必须如实显示等待领取。不得使用未授权的私有 IPC 或读取登录票据来绕过这个限制。

试跑完成回传后，才能启动本批来源核对和图种分组。分组清单须覆盖本批每篇文章，无法读取、缺图源和不确定语义须明确报告，不能视为无图。核对阶段不是按篇制作；核对完成后按逐图任务的 `group` 排序，跨作者同类处理。已完成试跑不重复派单。

## 部署契约

现有工作台服务导入 `workbench/workbuddy-http.mjs`，调用 `createWorkBuddyHandler({root,origin,config,publish,restore})`。在已有 Host 检查后、普通静态路由前调用返回的 `handle(req,res,url)`。`root` 为仓库外持久任务目录。`publish` 将已校验产物接入当前模型；`restore` 恢复已回传任务。现有修订回放在此后运行，避免旧制作稿覆盖新修订稿。

`workbench/workbuddy-candidates.mjs` 提供现有文章/图件数组的候选激活适配器。接入时必须保留批注及原验收记录，新输出标为待终审，其他未完成图件标为待制作，不自动计算为已通过。

前端在 `#toolbar` 后加载 `workbuddy-ui.js`，复用工作台 Tabler 样式。服务提供同名静态 JS 入口。公开代码不包含本机路径、原稿、运行认证配置及候选图。

仓库外 `config` 包含：

- `workerToken`：本机生成的随机凭据，只供执行器回调；禁止放入浏览器或 Git。
- `pilot`：`key,label,group,articleId,figureNumber,mainNumbers,outputNumbers,sources,instructions`。sources 每项为只读文件 `path,sha256`。
- `catalog`：`batchHash,articles,archive,groups,completedKeys,productionInstructions`。articles 每项为 `id,author,title,word:{path,sha256}`。
- `inventory`：来源核对任务，`kind:"inventory"`，包含唯一 key、label、group、sources 和核对指令。

把 `workbench/workbuddy-skill/SKILL.md` 安装到 WorkBuddy 用户技能目录，并在旁边写入仅本机使用的 `connection.md`，提供 RUNNER、CONFIG、仓库、Python、字体 profile 路径。执行器 CONFIG 仅含 `origin,workerToken,session`，不提交 Git。

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
| `complete <lease.json> <result.json>` | 校验来源、图号、产物路径/格式/哈希，再激活待终审稿 |

暂停不会强杀 Adobe。继续或失败重试生成新 attempt 目录，保留旧日志和候选。两分钟无心跳只代表待核实，原租约可续接；不能据此断言原进程死亡或启动重复制作。工作台重启同样保留原租约。明确确认旧执行已停止后，才允许对中断任务重新排队。

成图结果结构见执行器技能。分组结果为 `evidence,articles`；每篇含 `articleId,evidence,figures`，每张含 `number,group,outputNumbers,evidence`。阻塞项附 `blocked:true,problem`；整篇阻塞 figures 为空。确认确实无图须附 `noFiguresConfirmed:true`。保存和机械检查均不代表用户验收，整批放行仍须用户明确“全过了”。

## 验证

`node --test workbench/workbuddy-*.test.mjs` 验证队列、来源变更、身份、暂停恢复、心跳重连、HTTP 授权、CLI 日志和产物回调。HTTP 测试使用传输夹具，不是实际制图验收。真实接入还须用 WorkBuddy 执行一张图、人工核对源件和最终 PDF，并在浏览器确认待终审预览；这三步不能用单元测试代替。
