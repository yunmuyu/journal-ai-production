# 期刊图件直接 PDF 引擎

> 本引擎随 r32 正式基线交付。安装与验收见 [发布指南](../../docs/RELEASE-GUIDE.md)，普通任务入口见 [制作入口](../README.md)。内部 `0.2.0rc1` 与下文旧“候选”标记保留为组件开发沿革；整体发布身份以根目录 `RELEASE.json` 为准，具体能力仍按 `docs/CAPABILITIES.json` 的各项开关判断。

对话/Agent 入口已接通。来源、视觉与语义复核仍需执行；引擎只生成候选，正式交付由 localflow 管理。

先读 **AGENT.md**，使用说明见 **docs/AGENT-ENTRY.md**。新增能力与边界机器可读表：**docs/CAPABILITIES.json**。

## 本轮新增

原始 PDF / Matplotlib 类 SVG / PPTX / 位图 → 原生对象或几何候选证据 → Agent一次确认语义 → 自动生成制作说明 → 既有规则与布局 → PDF和实际检查。

Agent通过候选ID引用原文、刻度和图例，不用再写精确裁切和逐图画图脚本。位图候选可能误报，不允许未经核对自动清掉数据。默认8pt先排，原有小数整图适配及6pt下限不变。

互不串联的多个流程可使用 `kind: "columns"` 和 `columns` 语义数组。每列独立使用通用 graph 布局；列 ID 作为对象命名空间，标题可选，列距与顶对齐由公共规则计算。`relations` 只记录跨列异步关系说明，不生成顺序流程边。

开发适配器 `model: grouped-chains` 支持两个上下容器、相反水平链及可选外部桥接节点；标题和节点均绑定来源，坐标由测量约束生成。仅合成测试覆盖，不能当作任意分组图支持或单栏适配保证，详见 [GROUPED-CHAINS.md](docs/GROUPED-CHAINS.md)。

原生PDF图件支持文字/路径提取和框图说明编译；**任意PDF统计图的自动清字/图例去除未接通**。标准Matplotlib对象和已确认朝内刻线位图统计图有可运行路径。

## 安装与验证

Python>=3.11。创建独立虚拟环境后 `python -m pip install -r requirements.txt`。已有环境可先运行 `python -m journal_pdf doctor --output doctor.json`，不要反复安装或扫描系统。

`python -m pytest -q` 运行软件回归（需要显式配置测试字体，源码不附带字体）。正常生产不逐图重跑整个测试集。

源码不含作者素材、字体、密钥、缓存。字体从已有配置读取，缺失不隐式替代。已知的 Linux 预览配置不是刊物生产字体。

## 旧后端入口

原有 render/batch/serve 保留；下方为历史后端说明，新增入口及现行边界以上述文档为准。

---

# v0.1.2.1 增量候选

本版修复已确认的轴单位斜杠规则；不声称完成首次自动识图提速。见docs/NEW-v0.1.2.1.md及docs/FIRST-PASS-SPEED.md。以下旧版本说明保留。

# 期刊图件直接PDF候选模块 v0.1.1

本版是规则复用修订，不是全规则验收完成。先读 `docs/RULE-COVERAGE.md` 和 `docs/RULE-SOURCES.json`。

直接输出PDF，.ai不是必交。支持受控图件说明驱动的框图、流程图、统计图原图形保留和文字重排；不声称任意截图一键识别无误。

## 查看与运行

试用包可先打开 `开始这里.html`，查看sample-output中的实际PDF和预览。正式本机测试另用新输出目录，不能复用旧规则通过记录。

```text
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m journal_pdf fonts --profile config/fonts.production-windows.json
python -m journal_pdf batch private-samples/batch.json --profile config/fonts.production-windows.json --output local-output-v011
python -m journal_pdf serve private-samples/batch.json --profile config/fonts.production-windows.json --output local-output-v011
```

`fonts.production-windows.json`由本机按example配置，不包含在交付包中。只需配置一次；后续按已指定文件做轻量状态核对和缓存复用，不遍历字体目录。源码净包没有private-samples，需在本机另外提供真实样本；examples中为合成示例。

## 本版主要变化

数值三位一空在测量之前处理；菱形移植正式runtime校准公式；普通框增加实际墨迹留白检查；流程直接箭头使用3mm基础、标签按实测避让；完整等比适配允许6～8pt小数，低于6pt阻断重排；最终路径0.5pt与文字纯黑检查；实际PDF裁边0.25pt；图外7pt身份汇总；引擎/规则改变使旧审核缓存失效。

本批SVG线宽按新规则规范化，但路径和dash属性保留，位图曲线没有重画。任意SVG变换或PDF内容流的线宽改写不在本版自动支持范围。

## 边界

当前替代字体样张不等于宋体/汉仪中宋简/Times New Roman验收。复杂图种、公式、上下标语义、全部图例墨迹净距、单位规范、Word归属、InDesign及PDF/X仍有待验证项。永不自动标记正式放行。

代码与样图仅存独立候选目录；本机试用包含真实作者素材，不能整体上传GitHub。源码净包不包含素材和字体，适合人工审查后放入候选分支。
