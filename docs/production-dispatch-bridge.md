# 图号到现有执行工具的派发桥接

统一requests / production-runner现在按已确认路线分流，执行仍由原PDF入口及raster-batch承担。

## 单源位图新任务

完整方案使用raster-preserve时，不再要求预先拥有job ID或PDF render/spec。程序核对当前图件、文章、完整图号集合、原包/Word及源哈希，生成任务、来源注册、路线、证据、冻结清单与自动计划，再交给原raster-batch执行。

仍须有标准来源审核、history、允许修改、不变内容和独立加工决定：`productionRoute.processing={operation:'preserve',basis:'具体核对依据'}`，`qualityRoute:'raster'`。rasterReason和文件格式不能替代加工决定；缺项派发前拒绝。

`rasterAutoPlan`默认`{crop:null}`，保留完整原图。明确裁区可显式提供。不因专业图或截图分类自动决定是否换字。当前自动适配是一主图单源单输出；组合、多输出继续已有显式raster-batch入口，不把适配器限制说成引擎不支持。

原加工、质量门、自检封装、回传、可见回执和去重均保留。库调用不向stdout插入进度JSON，使用onResult回调；上层CLI保留一个完整最终JSON结果。

## 分类传到任务

`productionTaskGroup`将已绑定的classificationEvidence继续传到候选任务group，避免准入接受纠错后又用旧figure.type派发。Word、源文件、版本和已确认路线检查仍有效。当前两批已授权的流程图类别已补到本机服务配置，批次白名单不变。

## Office来源准备

`workbench/office-source-preparation.mjs::prepareOfficeSource`调用已有`lib/convert.mjs::convertOffice`，适用于Word、EMF/WMF、VSD/VSDX等。不得因为fitz不识别或Add-Type被禁就宣布缺源。

入口校验源和转换件哈希并复用缓存。同进程Office请求排队，等待计入时限；超时保留不确定标记供检查，不盲目继续开启Office。Adobe特殊路线的串行约束不变。

派发前来源检查已接入上述转换。prepared-intermediate仅说明来源可读，不等于成图。整篇Word导出PDF必须先确定本图页和裁区，不把全文文字绑定为某张图；分页、组合、转曲文字及实际加工要求仍需核对。

## 状态保护

服务运行时不要手动移动job目录或修改prepared.task。已发生目录被改名归档后内存仍保留running记录；这是内存与磁盘状态不一致，不是图种能力不足。保留现场，停止执行后使用既有恢复流程集中重载，不循环重启，不改变验收。

接单计时仍从最初提出图号开始；修工具后的执行验证必须单独标注，不用改requestedAt隐藏历史失败和准备时间。
