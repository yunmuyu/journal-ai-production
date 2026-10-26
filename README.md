# 期刊 AI 生产工作台

用于期刊图件的来源核对、保留原图加工、公共排版、PDF 检查、候选复核与受保护交付。当前正式基线为 **2026.10.26-r36-figure-audit**，整合已合入的 r33—r35 能力及本轮通过回归的换字、来源审核和排版修复。密集数值箭头标注仍是未通过试验，不在本版启用。

[下载正式版](https://github.com/yunmuyu/journal-ai-production/releases/latest) · [安装、升级与回滚](docs/RELEASE-GUIDE.md) · [更新日志](CHANGELOG.md) · [本版验证与边界](release-notes/2026.10.26-r36-figure-audit.md)

## 选择入口

| 用途 | 入口 | 说明 |
|---|---|---|
| 普通制作与已有稿修订 | [portable-production](portable-production/README.md) | preflight 核对输入，localflow 管理状态，direct-pdf 制作与检查 |
| 批量任务证据与独立复核 | [任务质量协议](portable-production/task-quality-workflow.md) | 输入契约、产物检查、复核记录；不替代视觉与语义判断 |
| 需要工作台或原生 Adobe 格式 | [兼容路线](docs/RELEASE-GUIDE.md#工作台与-adobe-兼容路线) | 保留 workbench、production-runtime 和协作工具，使用完整源码 |

生产顺序：查历史成稿 → 核对当前 Word 与图源 → 选择支持的加工路线 → 生成候选 → 自动检查与实际视觉复核 → 发布 → 登记用户终审。已有稿优先修订；已验收文件受哈希保护，不能由普通候选覆盖。

## 快速开始

1. 从 Release 下载 `journal-ai-production-…-portable.zip` 与 `.sha256`，按安装指南校验后解压。
2. 使用 Python 3.11 或以上版本；复用已验证环境，或在独立环境安装锁定依赖。字体、Cairo DLL、Adobe 不随包分发。
3. 在包外准备机器配置和合法字体，运行依赖检查、字体检查与一次真实样本验收，再开始新批次。

```powershell
python scripts/release_bundle.py verify --root .
Set-Location portable-production
python -m localflow --help
python -m localflow --config <包外的配置.json> status
```

完整配置、字体检查和首次样本步骤见[安装指南](docs/RELEASE-GUIDE.md)。包校验或命令启动成功，仅说明相应检查通过。

## 发布与维护

- 正式版本以 Git tag、GitHub Release、`RELEASE.json` 和下载包校验和共同确定。`files` 保持旧 runtime 安装契约，`portableFiles` 锁定当前制作程序。
- 后续小修从此基线建立短期分支，带针对性回归与更新记录发布补丁；不重写既有历史。
- 仓库保留完整工作台与兼容工具。轻量包只含当前制作路线；GitHub 自动生成的 Source code 包包含完整仓库。
- 作者 Word、图件、字体、机器配置、缓存、生产台账和过程截图不进入公开发布包。交接这些资料应使用授权的私有归档。
- `HANDOFF-*`、旧 release notes 与 `CLOSEOUT-STATUS.md` 是历史证据，不代表当前任务状态。组件内部旧版号记录其沿革，整体交付版本以根目录 `RELEASE.json` 为准。

## 验收边界

软件测试、PDF 解析/渲染、字体描述完整性、视觉审核、InDesign 实际置入和印刷验收是不同检查。正式发布不表示任意图种全自动合格，也不表示已认证所有 Adobe、印刷 RIP 或新机器环境。统计图不得根据猜测数据重绘；不支持的输入应保留原件并明确转人工处理。
