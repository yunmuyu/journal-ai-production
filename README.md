# 期刊 AI 生产工作台

唯一生产入口为 `node journal.mjs`。工作台、PDF、JPG和批量回传共用一份外置配置，不另选私有server、localflow或旧runtime。新电脑按[安装说明](docs/NEW-COMPUTER.md)接续。

[下载当前生产版](https://github.com/yunmuyu/journal-ai-production/releases/latest) · [安装、升级与回滚](docs/NEW-COMPUTER.md) · [更新日志](CHANGELOG.md)

## 内部组件

| 用途 | 入口 | 说明 |
|---|---|---|
| 普通制作与已有稿修订 | [portable-production](portable-production/README.md) | 核对来源与路线，公共 raster 处理JPG，direct-pdf处理可编辑PDF，独立质量门检查 |
| 批量任务证据与独立复核 | [任务质量协议](portable-production/task-quality-workflow.md) | 输入契约、产物检查、复核记录；不替代视觉与语义判断 |
| 工作台派单、反馈与候选回传 | [执行器接入](docs/workbuddy-executor.md) | 兼容Agent领取持久任务，按路线调用公共工具，回传待终审 |
| 必要特殊格式或原生 Adobe 格式 | [兼容路线](docs/RELEASE-GUIDE.md#工作台与-adobe-兼容路线) | 保留production-runtime和协作工具；常规照片、截图与组合JPG不依赖Photoshop |

生产顺序：查历史成稿 → 核对当前 Word 与图源 → 选择支持的加工路线 → 生成候选 → 自动检查与实际视觉复核 → 发布 → 登记用户终审。已有稿优先修订；已验收文件受哈希保护，不能由普通候选覆盖。

## 快速开始

1. 从 Release 下载 `journal-ai-production.zip` 与 `.sha256`，按安装指南校验后解压。
2. 使用 Python 3.12 或以上版本；复用已验证环境，或在独立环境安装锁定依赖。字体、Cairo DLL、Adobe 不随包分发。
3. 在包外准备机器配置和合法字体，运行依赖检查、字体检查与一次真实样本验收，再开始新批次。

```powershell
python scripts/release_bundle.py verify --root .
node journal.mjs doctor
node journal.mjs produce --input '<期次目录>' --output '<交付目录>'
node journal.mjs start --config '<机器配置.json>'
node journal.mjs produce --config '<机器配置.json>' --request '<本轮任务.json>'
```

不带工作台的做法见 [无头生产](docs/无头生产.md)。现行尺寸、字体和留白以 [规则对照](docs/规则对照.md) 为准。工作台仍可用于审校，默认不必启动。Illustrator 保留给合并和本机交互，不作为画图路线。

produce委托现有production-runner，JPG由同一执行器分流raster-batch。内部组件文档的直调示例只用于开发和特殊兼容，不是其他生产入口。具备条件时至少5图并行，Adobe串行；已有候选先复用，卡点记录并跳过，终审由用户完成。

### 本地交付目录清点

从已核对的 Word 图号准备包外 JSON。例如目录内有“01 示例作者”，图 2 已确定拆成两个分图：

~~~json
[{"folder":"01 示例作者","author":"示例作者","numbers":["1","2.1","2.2"]}]
~~~

~~~powershell
node journal.mjs inventory --input '<交付根目录>' --expected '<预期图号.json>'
~~~

命令仅扫描指定作者目录的根层，按“作者-图号.pdf/.jpg/.jpeg”识别成品。缺图、额外图号、重复格式、主图与分图混放均报告并返回非零。清点通过时，标准输出按预期清单顺序列出相对路径和 SHA-256，可用于汇总置入前对照。这一步只核对交付集合，PDF 内容、字体与视觉仍由各自的质量检查核验。

临时探查成品 PDF 或原图可使用公共 PDF 环境中的 `python -m journal_pdf inspect <图件路径> --output <报告.json>`，查看 PDF 页尺寸、字体、文字、矢量路径和图像资源。可编辑成品的字号、线宽和渲染灰度继续复用 [direct-pdf 的成品审计](portable-production/direct-pdf/README.md)。

## 发布与维护

- 正式版本以 Git tag、GitHub Release、`RELEASE.json` 和下载包校验和共同确定。`files` 保持旧 runtime 安装契约，`portableFiles` 锁定当前制作程序。
- 后续小修从此基线建立短期分支，带针对性回归与更新记录发布补丁；不重写既有历史。
- 仓库保留完整工作台与兼容工具。本迁移包包含当前制作路线、工作台与公共脚本；GitHub 自动生成的 Source code 包包含完整仓库。
- 作者 Word、图件、字体、机器配置、缓存、生产台账和过程截图不进入公开发布包。交接这些资料应使用授权的私有归档。
- `HANDOFF-*`、旧 release notes 与 `CLOSEOUT-STATUS.md` 是历史证据，不代表当前任务状态。组件内部旧版号记录其沿革，整体交付版本以根目录 `RELEASE.json` 为准。

## 验收边界

软件测试、PDF 解析/渲染、字体描述完整性、视觉审核、InDesign 实际置入和印刷验收是不同检查。正式发布不表示任意图种全自动合格，也不表示已认证所有 Adobe、印刷 RIP 或新机器环境。统计图不得根据猜测数据重绘；不支持的输入应保留原件并明确转人工处理。
