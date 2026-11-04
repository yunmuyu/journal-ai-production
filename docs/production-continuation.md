# 生产接续：重试、分类纠错与 SVG 预览

继续使用 production-runner / requests / raster-batch，不新建执行器。

图号到raster任务、任务分类传递及Office来源准备的新接入说明见 [production-dispatch-bridge.md](production-dispatch-bridge.md)。

## 重试

requests 保留配置中的显式 `retryFailed:true`，默认不自动重试。失败修复后使用同一方案、同一接单时间接续。不能通过重写 requestedAt 伪造三分钟达标；相同方案显式重试保留最早已记录的接单时钟，超过窗口即记录超时。真实的新一轮须单独记录轮次与前次失败，不改写前次耗时。

不完整 pdf-candidate 目录已有普通/修订新 attempt 接续逻辑，必须通过统一入口调用。不手工删除目录、篡改 prepared.task 或反复新建任务；同源同版本已知故障先修原因，再显式重试。

## 旧启发式分类与来源冲突

不能依据文件后缀或单一解析错误改判。原图语义已核实、旧 row.type 确实错标时，在现有方案附上来源绑定的分类纠错：

```js
import {prepareClassificationEvidence} from '../workbench/production-admission.mjs';
plan.classificationEvidence = prepareClassificationEvidence(
  liveFigure, plan,
  {kind: 'diagram', basis: '具体来源对象及 Word 图题说明为何是流程图'},
  externalEvidenceFile
);
```

工具自动绑定图件、当前 reviewVersion、完整输出图号、原包/Word/选定源哈希，并复核实际文件。只接受 diagram/chart，不以此授权灰度 JPG 降级；用户已确认分类不能被代理覆盖。分类纠错供准入和执行时路线发现共同使用，任何绑定变化需重新核对。它不是用户终审通过，也不自动修改工作台历史分类。

## SVG HTML 标签预览

只在 foreignObject 的原生 text 回退内容一致时去除 HTML 重复分支；保留 switch 上的 transform/style/clip。外链仍拒绝，唯一豁免为既有 drawio 导出说明链接的点击目标。

遇到 `preview_svg_fallback_mismatch`，应检索完整来源的可靠预览/转换路线；不能使用截断回退、把它解释成缺源或放宽质量门。来源原字节不改。已有回传候选保留，预览失败不擅自改变用户验收。

## 下一轮

先读主配置和最新接手记录，用至少五张独立且真正具备条件的未完成图运行；必要检查通过即回传。照片、截图、专业图不能仅凭分类就选 raster-preserve，仍需核对有无换字、重绘、拆分和灰度辨识要求。单图卡住留证转下一张，统计真实渲染并发与工作台可见回执。
