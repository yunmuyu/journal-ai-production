# 已有能力检索与失败分流

遇到导入失败，先区分“当前入口不支持”“已有兼容入口未调用”“原生软件调用失败”“内容/质量门未通过”。不能仅凭 direct-pdf 的 unsupported_native_source 判定项目没有该格式能力，也不因此整图栅格化或重写导入器。

## 已有入口

| 情形 | 复用入口 | 边界 |
| --- | --- | --- |
| VSD/VSDX/VSDM 转 PDF | `lib/convert.mjs` 的 `convertOffice(jobRoot, source)`，调用根目录 `scripts/convert-office.js` | 使用 `Visio.InvisibleApp`，不能只检测 `Visio.Application` 后判缺少 Visio。原件只读副本转换，有源与输出哈希缓存。 |
| Visio 指定页 SVG | `collaboration/scripts/prepare-visio.mjs --config MACHINE JOB SOURCE PAGE` | PAGE 是已核对的源文档页号；保留默认 PDF 路线。入口有缓存，勿重复准备。 |
| 原 SVG 对象组 | direct-pdf 的 `source_svg_groups.py` | 显式对象身份与裁切；不是任意 SVG 自动识别/排版。 |
| 白色矩形遮罩的 SVG | `python -m journal_pdf prepare-svg-pdf SOURCE.svg --source-sha256 SHA256 --output OUTPUT.pdf --report REPORT.json` | 在现有固定 direct-pdf 环境调用。只自动处理无样式表、单个不透明白色矩形及唯一引用的遮罩；其他遮罩明确拒绝。输出是原矢量中间件，需继续灰度、换字及回传，禁止当成成图。 |
| 曲线与图例候选 | `python -m journal_pdf propose-chart-series SOURCE.pdf --source-sha256 SHA256 --frame X0 Y0 X1 Y1 --plot X0 Y0 X1 Y1 --swatch LINE_INDEX MARKER_INDEX --output REPORT.json` | 可重复 `--swatch`；源图例框、绘图区及样符索引必须按本图提供。支持分段曲线，报告只提供候选，须核对当前文字与系列并执行现有源绑定和最终 PDF 检查；不复制其他图的数据。 |
| PDF 混合矢量/图片 | direct-pdf 的 `source_mixed_body.py`、`source_native_gray.py` | 保留原对象与归属证据；不能把中间转换成功当完整回传合同。 |
| JPG/PNG 保留内容 | 公共 `raster` 与 `workbench/raster-batch.mjs` | 免 PS；来源、布局、灰度及独立回传检查仍必需。 |

Visio 历史实测见 [返工优化记录](../collaboration/下一批返工优化-20261012.md)和[工具交接](../collaboration/20261012-tool-handoff.md)。已有三份选页导出与重复缓存记录；文字重叠、渐变等风险仍需针对当前源核对。根目录研发驱动与 `production-runtime/` 的已发布副本有功能差异，不得整目录互覆。

## 失败后只处理缺失环节

- `0x80010001` / `-2147418111` 表示 COM 调用被拒绝；记录入口、原始码、耗时和结果文件。不能改写成“未安装/不支持格式”，不能关闭用户软件或无限重试。
- 当前源和已有候选身份、哈希吻合时复用；辅助核验失败不自动意味着候选图内容错误。
- 源 PDF 缩放后字号会变化。内容核验与目标字号/栏宽检查分别执行，不能要求缩放前后字号完全相等。
- 柱图的 patch、图例、数值标签必须绑定完整；没有可靠映射就挂起该入口。整幅原对象保留路线已接续时，不重复跑已知失败的统计图解析入口。
- 数字总量一致不等于数字排版通过。窄图的相邻刻度可能被 PDF 文本提取合并，先按实际容量调整布局，再验证原数字检查；不删门禁。
- 源转曲字仍是转曲字。中间 PDF 保留了矢量/图片，不自动意味着文字可编辑、字号合规、已经回传或可以刊用。

侧边修复包应带受影响文件、哈希、测试和未覆盖项，由当前唯一生产写入者接入。原对象路径已在处理的图不重复领取；候选回传与用户终审保持分离。
