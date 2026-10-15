# 接入约束：现有Agent入口，非独立上传网站

基线：ced82c85cb1a8490c52750e772a9415e6ac705f6 / r21。此候选新增目录，不修改正式runtime、生产台账或已验收成果。

## 两阶段协议

`scan(manifest, out)` / CLI `probe` 一次读取源，输出探查JSON、媒体、draw.io结构和匹配候选；不把图形或公式读错后强行归类。匹配算法的尺寸/像素近似仅作为候选证据，不能独立确认身份。图片原生图题与正文引用、Word媒体成员数、主图数、内部面板数、PDF源页数和交付数分开。

Agent对原图和证据做语义核对，填写review：snapshot、figures、identity、sources、selected_primary、export、route、protection、layout、issues、rules。`apply_review(probe, review, manifest)` / CLI `route` 核验当前文件快照、图号与所选源对象存在性，产生只读路由结果。原始HTML上下标与geometry_xml保留，不用扁平文字替代富文本母版。

## 硬约束与未完成门禁

Word范围、完整图号、已确认栏宽及同图纠正不得降级成可忽略字段。来源探查可先并行，正式生产仍依赖身份和范围确认。当前A/B/C/D仅供Agent建议展示，不要求用户逐图确认图种，更不独立授权发布。

默认8pt；现行6至8pt允许小数的完整图形适配规则保留，不按旧顺序机械生成8/7/6三套成品。推荐栏宽、Word放置宽度、CSS诊断不是真实字体容量通过。颜色需求不是source-color批准；保护热图/照片证据与出版颜色授权分别检查。缺.ai不阻塞PDF路线，数据、字体、颜色、实际PDF及版面审计不删除。

内容不一致单独记录，不改写原稿、不自动补节点、不按表格覆盖曲线；不受影响的提取可继续。没有原始数据不重建统计曲线。图例遮住原数据不能通过清字后补画弥补。

## 兼容既有决策

正式消费前仍需现有find-prior-artwork.mjs、prepare-decisions.mjs、本机最新inventory/production-results/evidence及用户纠正。无本机记录时标为未读取，不伪称已检索无匹配。历史案例不只是图种标签匹配。

`bridge_legacy()`仅在完全相同的显式figure ID下加入aiProposal.preflightV2。原productionDecision、caseRetrieval、userCorrectionContext及确认/验收历史不变；既有preflightV2变更记录进历史，重复同一报告不重复追加。已确认栏宽发生冲突时增加待核门禁，不覆盖原决定。其他旧字段结构仍需正式消费端按本机契约读取，不能由此桥接函数代替全量生产准入。

## 范围与测速

已实现的是源探查、原生draw.io提取、Word媒体关联、候选匹配、Agent路由、源hash失效及兼容桥。未实现任意截图可靠自动识字、复杂图件通用重排、自动安全清字区或最终生产PDF。

探查程序耗时不包含Agent视觉语义、工具往返、研发适配与成品制作。未提供独立盲测证据时，不自动纳入首次生产速度统计。开发样本与冻结引擎后的新样本必须区分。

安全：拒绝XML实体与不安全ZIP路径，限制输入及解压体积；不执行SVG脚本/外链。活动内容标记不是完整安全沙箱证明，后续渲染仍需独立沙箱。真实原稿和作者报告留在外部结果包，公开代码只含合成测试。
