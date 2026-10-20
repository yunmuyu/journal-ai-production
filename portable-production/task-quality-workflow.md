# 多代理质量优先工作流（可选小样本路线）

此流程复用 `task_quality` 证据门禁和原 `localflow` 生产能力。它不改变已发布CLI默认行为；先对未冻结小样本使用，验证后再扩量。**不能凭本文件声称已经覆盖全部生产任务或形成OS隔离。**

## 责任与阶段

1. 主代理从当前Word、真实图源、历史成稿、最新反馈和accepted记录确定一个图件身份；所有输入逐项hash绑定。
2. 主代理填写不可变契约：producer、专业路线、允许变化、不得变化、交付target、独占workspace、机械/人工核对项和最多2次局部修复。每次新尝试保留旧记录。
3. `precheck` 通过后才委派。已有可复用成稿不得因为工具升级重新制作；冻结目标由现有正式修订流程处理，不能用普通新任务解锁。
4. 生产者只在workspace产出候选、已有审计和源对照，不自行Copy到作者目录；同类先完成一张，经主审后再扩量。
5. `postcheck` 自己核实际产物集合、格式、宽度、描边/像素、hash并重生预览；成功仍只是candidate/manual pending。
6. 主代理或一个独立于producer的复核者实际打开源和最终预览，逐项记录观察。不能只复述生产者声明。图种专业项不能省略。
7. `finalize` 封存回执，`verify` 在调用原localflow review/publish前复验。继续使用原来的来源、候选、writer lock、旧target hash、归档、原子替换和人工终审保护。
8. 用户终审与内部review是不同状态。收到反馈后记录figure ID、artifact hash、rule ID、实际问题和修复范围；下一次契约读取这些记录，不重做其它已过图。

## 委派包与上下文

优先给fresh-context代理一个有界包：contract文件与hash、已precheck的envelope、源文件清单/预览、当前图件反馈、公共工具入口/限制、独占目录、交付要求和失败处理。不要靠完整历史fork替代明确约束。包中的历史结论、目标宽度、来源优先级不得由后续代理擅自降级。

发出任务前核代理真正可用的工具/角色和本机环境。需要源图理解时必须实际读取源图；不能只给正文摘要。可访问同一工具不等于适合相同任务。模型本身、角色职责、机械规则是三个不同层次。

示例委派骨架（替换全部占位符）：

```text
负责 <figure IDs>，producer=<agent ID>，唯一写入范围=<workspace>。
先读 <contract> 与 <envelope>，source/hash和本次允许变化以契约为准。
你不是独自在代码库，保留其他人的工作；不要改生产release/作者目录。
只复用公共字体/布局/审计，不复制一套私有算法。
先完成一张候选：实际PDF/JPG、源对照、现有审计及未覆盖项。
提交postcheck结果仍不是最终通过；不得自行发布或替主代理签review。
同规则重复失败两次，提供输入/错误码/几何证据，停止扩量并报告公共卡点。
```

## 专业化任务配置

以下是任务契约和提示中的职责配置，不冒充已加载的Codex自定义agent。当前工具确实支持角色时再选择对应角色；不要写一个TOML就声称运行已采用。

| 路线 | 生产者重点 | 建议manual_review附加项 |
|---|---|---|
| diagram | 源节点/边/分组/行列、普通直角框、真实墨迹尺寸、同轴直连、标签归属；不自增节点、不改源拓扑 | topology、label_ownership、source_icons、spacing_and_strokes |
| circuit | 保留真实器件/引脚/网名/导线；符号、单位、斜体下标；mask匹配真实底色；无非等比拉字 | topology、label_ownership、units_and_symbols、mask_background |
| source-preserving-chart | 保留真实数据主体像素/矢量；不估数重绘；系列/图例/轴/单位对应，灰度后可区分 | data_geometry、legend_and_axes、units_and_symbols |
| raster | 输入优先原附件；像素/DPI/实际宽度；需要PS时有真实PS bridge证据；按已确认格式交付 | source_quality、processing_trace、crop_and_readability |

全部路线都需要source_content、visual、runtime_provenance。图/电路强制含topology和label_ownership。自动门禁的最低集合不等于完整专业验收；主代理为该图增加具体项目，例如“3组指标均在采集源框上方各自竖线旁”，不能只写“布局美观”。

## 自动项与人工项的边界

- 文件hash、来源是否变更、目标是否冻结、workspace占用、实际格式/像素/DPI/物理宽度/可识别矢量描边，适合确定性脚本。
- 对反复退修的框距、同轴连线和标注分区，委派前明确对象ID与关系配方，复用quality-recipes/diagram-relations.mjs检查公共生成器实测Scene。横向净距扣除两侧半描边；标注必须落在指定走廊且靠近指定路径。该检查只覆盖配方声明的关系，不替代实际PDF与源图语义核对。
- Scene-owned对象可用现有Scene门禁。导入PDF/SVG的未注册框和线不能因为Scene返回0就说检查过。
- 语义、图标保真、标注归属、灰度图例可辨、公式/电路含义必须对源实看；自动未知保留pending。人工解决后receipt仍保留自动未覆盖记录。
- 同轴直连按最终路径共线性和可见形状验收，不把“直线”误写成via必须为空。当前公共exact_terminal箭头需要3mm末段，允许同轴终端waypoint；任务前先核生成器接口，不能用错误的调用约束制造无效重试。
- 所有数值来自实际测量，不写死“0.5=true”“非标准路径=[]”。报告绑定实际output ID/hash，不能拿另一图报告放行。
- 代码文件hash只证明指定字节，不能证明当时导入了该模块。runtime_provenance引用真实module.__file__/engine_signature/check_candidate结果；没有则保留未证实。

## 尝试、并行与成本

已有agent_entry局部重试/最多3次机制继续保留。任务通常先设2次局部修复；同类失败先诊断工具接口、路由约束与源配对，不整张盲生成。独立文章可并行，依赖同一公共补丁的任务等待验证；共享Adobe会话继续串行；一个目标仅一个发布写入者。

不为降低token而省源图和最终产物检查。先把确定性工作移到脚本，控制上下文和失败循环。简单任务以后可做低成本模型小样本A/B；高风险语义由主代理与最多一个独立复核负责。未经A/B，不保证换模型能降退修率，不批量修改模型配置。

## 指标与渐进推广

每图从下一批开始保存首次送审时间/hash、每次用户反馈、rule_id、局部修订次数、工具时间、模型响应usage及人工计时（未计填null）。一次交付合格率只统计首次送审，不能把修后通过率、自动拦截率或单元测试通过率代替。

先在克隆的真实样本上验证precheck→postcheck→独立review→verify；再接一个未冻结真实任务；连续记录后才比较人工退修变化。默认不上传私有图件做云端eval。回滚为停用这条可选流程；已有生产CLI、release配置和作者文件保持原状。
