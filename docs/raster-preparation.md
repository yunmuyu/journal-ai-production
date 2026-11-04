# 已确认位图的自动计划

从journal-runner 0.1.0吸收准备流程，复用本仓库raster引擎；没有部署其服务、台账、引擎副本或按扩展名自动决定加工路线。旧raster-batch清单不变，新清单可用autoPlan代替plan：

```json
{
  "id": "既有任务ID",
  "routeFile": "route.json",
  "evidenceFile": "evidence.json",
  "outputName": "figure-1.jpg",
  "autoPlan": {"crop": null, "quality": 95}
}
```

route仍须明确raster-preserve、processing.operation=preserve及真实依据、selected来源SHA、requirements.widthMm。evidence.runtime.python须为明确的解释器路径或path/SHA引用。plan与autoPlan不能同时提供。crop必须显式给null或EXIF方向纠正后的像素裁区；不自动裁白边、不猜图号、不通过插值伪造细节。组合图继续给完整显式plan，逐输出多图可各自使用autoPlan。

入口先执行共享故障拦截，再校验来源SHA，异步调用公共raster.load_input测量原始/方向纠正/裁切后的尺寸和有效源PPI，自动生成单图灰度计划。相同源路径、SHA、裁区和运行时在同批共享测量Promise；不同图件的制作与回传仍使用原并行池。测量记录写入本次attempt的source-preparation.json，不改作者原图。低PPI是实测事实，不代表内容不可用或自动通过；原质量门及用户终审保持原职责。

## 复用检索接口

raster-preparation.mjs还提供rasterReuseKey(context)及findAcceptedRasterReuse(context,records,currentAcceptance)。context绑定批次、文章、图件、输出号、当前Word SHA、源SHA、裁区、加工要求、布局、栏宽、质量、灰度权重、运行时和规则SHA。record包含key、figureId、acceptanceVersion、output:{path,sha256}。

检索必须读取当前权威验收记录：accepted=true且version与record.acceptanceVersion相同，输出字节SHA未变才返回候选引用。取消通过、验收版本变化、裁区/稿件/规则不同均不复用。它不会创建新台账、复制交付文件或自动批准另一稿件；现有工作台的已回传项继续走原alreadyReturned分支。跨历史版本的复用自动派发尚未接入，不能把此检索API称为已自动回传。

## 验证

使用WORKSPACE_TEST_PYTHON指定已安装Python，运行raster-preparation.test.mjs、raster-preparation-batch.test.mjs、raster-batch.test.mjs。覆盖真实公共引擎、旧计划/自动计划混跑、原质量门、HTTP回传、预览失败后续接、重复请求去重、来源/裁区限制和严格复用检索。测试使用独立临时工作台，不写正式稿件。

收益是减少逐图手写准备参数及重复测量，不改变渲染算法；未测得每小时实际生产增量，不承诺倍数提速。无需重启工作台服务；新的CLI调用加载入口，已有运行进程保持原代码。
