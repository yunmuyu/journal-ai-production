# 更新日志

发布版本以 GitHub Release 与根目录 `RELEASE.json` 为准。历史组件的内部版本号保留，不代表整套工具当前是否正式发布。

## 2026.10.27-numeric-tick-audit-fix

- 修复水平轴多位数刻度在 PDF 文本提取中合并为一行时被误报缺失的问题。数字检查改为按各刻度声明的页面区域提取词元，避免由审计误报触发不必要的刻度旋转或重新排版。
- 增加真实 PDF 回归：`10 11 12 13 14 15` 同基线合并提取时仍能逐项通过，真正缺失的数字仍会阻断。
- 测试夹具显式使用 UTF-8 读取字体配置，避免中文 Windows 默认 GBK 解码造成无关测试错误。

## 2026.10.26-r36-figure-audit

- 整合 r35 主线与已验证的来源/换字审核修复；入口先审结构与换字需求，不能以转灰度代替换字。
- 补充原生 PDF/SVG 文字登记、无绘制来源绑定、实际 PDF 字形与文字方向核对；来源、数据保护和最终视觉审核仍独立执行。
- 修复存储单位空格、树组间距、分支路由和嵌套 SVG 定义处理，并保留合成回归。
- 密集数值标注、箭头 callout、白底遮罩和自动统计图间距试验不纳入本版；原分支与试验资料保留。
- 本版验证结果与限制见 [发布说明](release-notes/2026.10.26-r36-figure-audit.md)，不自动部署。

## r33—r35 主线整合去向

r33（PR #10）、r34（PR #11）、共享 PDF 解码门禁（PR #12）已由 PR #13 整合为 r35 主线，r36 在此基础上继续整合。下方 r33 候选说明是当时记录，不代表当前仍待合并。批处理 PR #3、约束求解及未验证旧运行时仍保留候选。完整历史见 r35 发布说明。

## 2026.10.22-r33-layout-capabilities（历史候选，已整合）

- 增加可显式启用的双侧递归树排版，按叶到根测量并保留左右归属、嵌套关系和单栏约束。
- 流程图“开始/结束”使用胶囊形终止框，输出审计检查实际形状；普通处理框保持直角。
- 增加竖排混合文字支持，中文保持直排，英文词整体旋转。
- 直接 PDF 回归 520 项通过；工作台节点检查 51 项、发布包检查 3 项、引擎目录检查 2 项通过。

状态：候选 PR [#10](https://github.com/yunmuyu/journal-ai-production/pull/10) 的便携包检查已通过；真实图副本复核仍暂停，尚未合并或创建正式 Release。InDesign 置入、真实作者图件终审和印刷 RIP 不在本次验证范围。

## 2026.10.20-r32-production-baseline

十月生产公共能力的正式交付基线。后续以小范围修复和针对性回归维护。

- 提供当前制作路线的可复现 ZIP、逐文件清单和下载校验和；工作台与 Adobe 兼容工具保留在完整源码中。
- 发布密封同时覆盖 portable-production 与旧 production-runtime，不改变既有安装器的 `files` 契约。
- localflow 同时支持源码 `direct-pdf` 与既有安装 `engine` 布局；缺失或两套并存时明确阻断。
- 补齐安装、外置配置、首次验收、升级、回滚与维护文档。
- 纳入此前已合并的 PDF 字体兼容修复：实际 PDF 发布前检查字体描述；纯位图页中未使用的字体资源不误报。
- 真实视觉、公式与连接语义、InDesign 置入及印刷检查仍独立执行，软件检查不冒充终审。

本版新增测试和未验证边界见 [发布说明](release-notes/2026.10.20-r32-production-baseline.md)。

## 2026.10.20-r31-public-capabilities

整合已验证的公共制作能力，保留工作台与 Adobe 路线，明确私有素材不入库。[详细记录](https://github.com/yunmuyu/journal-ai-production/blob/main/release-notes/2026.10.20-r31-public-capabilities.md)。

## v2026.10.14-r21-common-contract

上一份 GitHub 正式 Release：通用制作契约与当时的停产交接。它描述的是历史状态，不代表现行制作暂停。[历史 Release](https://github.com/yunmuyu/journal-ai-production/releases/tag/v2026.10.14-r21-common-contract)。
