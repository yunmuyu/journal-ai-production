# 更新日志

发布版本以 GitHub Release 与根目录 `RELEASE.json` 为准。历史组件的内部版本号保留，不代表整套工具当前是否正式发布。

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
