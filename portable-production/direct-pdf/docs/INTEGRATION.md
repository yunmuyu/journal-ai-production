# 接回主工作台的方法

将**源码净包**作为独立候选目录置于 `candidates/direct-pdf`。不覆盖 `production-runtime`、`skill` 或 `RELEASE.json`；不改已验收记录。先读主仓库当前约束、本机最新版本与接手记录，避免并行 Agent 修改冲突。

当前 Node 入口：

```javascript
import {runDirectPdf} from './bridge/run-direct-pdf.mjs';
const result = await runDirectPdf([
  'batch', 'ABSOLUTE_BATCH_JSON',
  '--profile', 'ABSOLUTE_LOCAL_FONT_PROFILE',
  '--output', 'ABSOLUTE_NEW_CANDIDATE_DIR'
], {python:'ABSOLUTE_PYTHON_EXE', moduleRoot:'ABSOLUTE_CANDIDATE_MODULE_ROOT'});
// result.ok=true 只代表候选命令成功；不是正式验收。
```

桥采用 child_process.spawn 的参数数组，不拼 shell 命令，不调用 Adobe、不查字体目录、不写正式台账。当前没有实现跨线程重排：本地服务串行处理，字体在进程内复用。并行生产应分开候选输出目录，不并发改同一个批次。

正式交付合同应区分通用检查与后端专用检查：通用项仍包括来源、图号集合、PDF、字体、数据/拓扑、颜色、实际 PDF 审核及 hash；只有 Adobe 后端才要求 AI 专属证据。禁止为了满足旧六文件条件伪造 .ai。正式状态保护、终检权和已验收冻结规则不能取消。

solver bridge 仅接受已知模块路径；从原始 input.json 调用外部 solveLayout，保留 status、原返回证据与原结果文件。外部求解器仍需真实测字输入并与所用 PDF 字体一致，字体变化必须重新测量和求解。本候选没有把求解器“预算耗尽”当成功，也不将其毫秒级几何计时当全流程速度。

迁移时先选候选八图复制品做本机回归；完成后再扩量。不要因为软件路径升级而重做已验收图。具体正式清单的修改应在拿到当前本机代码后另做小分支；本包没有假定旧 GitHub 字节就是最新本机版本。
