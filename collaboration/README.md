# 双机协作入口

只维护一个代码库。各机在短期 task 分支修改、验证后合并；不长期维护家庭版和办公室版。仓库根目录是研发源码，`production-runtime/` 与 `skill/SKILL.md` 是 `RELEASE.json` 固定的正式发布副本；源码与发布副本不同时，源码是尚未发布的候选变更。切换机器不重制其他作者主图。

复制 `machine-config.example.json` 到仓库外的 `machine.json`，填写本机实际路径，不提交私人配置。F 盘固定入口按 `repo`、`releases`、`work`、`worktrees` 划分。`productionRoot` 指生产资料根，`releaseRoot` 指发布归档；`runtimePath` 指带版本号的固定 runtime 路径，不用 `current` 软链。`recordRoot` 指原权威作图记录，`pathMapFile` 是仓库外的路径映射 JSON，格式为 `{ "mappings": [["旧 Windows 前缀", "本机 Windows 前缀"]] }`。

```sh
node collaboration/scripts/install.mjs --config /path/to/machine.json
node collaboration/scripts/install.mjs --config /path/to/machine.json --apply
node collaboration/scripts/run.mjs --config /path/to/machine.json status /path/to/job
node collaboration/scripts/run.mjs --config /path/to/machine.json render new-job /path/to/plan.json
node collaboration/scripts/start-workbench.mjs --config /path/to/machine.json
node collaboration/scripts/start-workbench.mjs --config /path/to/machine.json --port 18742
```

安装器默认仅预览，`--apply` 才部署到 `skillsRoot/journal-figure-workflow`。它核对清单、Skill 哈希和 Adobe 全局锁，备份目标中将被覆盖的文件，仅复制发布清单列出的文件，不清理额外文件；安装回执是普通 JSON。运行入口每次校验 `runtimePath` 的全部文件；新 job 的相对路径优先在 `workRoot` 下，没有该字段时沿用 `workspaceRoot`。子进程工作目录为 `workspaceRoot`，相对 plan 路径也从这里解析。状态查询不写版本事件；其他命令在 job 下追加独立 JSON 行，记录实际发布版本、清单哈希、参数和执行结果。不要把凭据写进 CLI 参数。

工作台入口先设置 `recordRoot`、路径映射和 workspace 环境，再以 `workspaceRoot` 为工作目录加载 `workbench/server.mjs`，不执行任务调度。旧 C 历史 workspace 暂不迁移、也不全量清理；旧 job 可用绝对路径原地读取，新 job 放 `workRoot`。真实作者文件和 fixtures 不进入 Git；已安装 Skill 保留完整内容，当前没有宣称它已轻量化。Adobe 原生测试须在所用机器上另行串行执行。
