# 正式版安装、升级与回滚

## 获取与校验

下载 [GitHub Release](https://github.com/yunmuyu/journal-ai-production/releases/latest) 的便携制作包及对应 `.sha256`。它包含当前公共制作程序、示例与使用文档，不包含 Python、商业字体、Adobe、作者资料或本机配置。完整工作台与历史兼容工具使用同一 tag 的 Source code 压缩包或 Git checkout。

以下命令在 PowerShell 中执行，路径占位符需要换为本机实际路径。保留原路径含空格时的引号。

```powershell
Get-FileHash "<下载的portable.zip>" -Algorithm SHA256
# 对照下载的 .sha256；不一致时停止解压使用。
Expand-Archive -LiteralPath "<下载的portable.zip>" -DestinationPath "<新版本目录>"
Set-Location "<解压后的journal-ai-production-版本目录>"
python scripts/release_bundle.py verify --root .
```

ZIP 校验和是下载完整性检查；`verify` 逐项验证包内文件的大小与哈希，不是数字签名，也不会自动删除运行后产生的额外文件。

## Python 与依赖

要求 Python ≥3.11。本版实际测试环境和结果见 release notes。已有已验证环境可以复用；新环境需完整检查，不能用本机测试代替新机验收。

```powershell
python -m venv "<包外的环境目录>"
& "<环境目录>\Scripts\python.exe" -m pip install -r portable-production/dependencies.lock.txt
```

锁定列表来自生产环境，不表示每种 Python/操作系统都有匹配 wheel。若安装失败，停止该路线并记录缺失项。Windows 上 CairoSVG 还需要可加载的 Cairo DLL；pip 安装成功不代表 SVG 路线可用。不隐式安装 WSL，不把缺依赖的图自动转成位图。

## 配置与首次运行

把 `portable-production/config.example.json` 和 `portable-production/direct-pdf/config/fonts.production-windows.example.json` 分别复制到包外私有目录。

- 配置中的 `delivery_root`、`state_root`、`cache_root` 和 `font_profile` 填绝对路径。交付与状态目录相互独立；缓存不得放进交付目录。`workbench_enabled` 保持 `false`。
- 字体配置填写本机合法安装的实际字体文件与集合索引，先核对名称。不得把 Linux 预览字体当作刊物生产字体。
- 机器配置和字体不进入 Git，不随公共包升级覆盖；本文命令中的 `<python>` 指刚选定的 Python 可执行文件。

```powershell
Set-Location portable-production/direct-pdf
& "<python>" -m journal_pdf doctor --output "<私有检查目录>\doctor.json"
& "<python>" -m journal_pdf fonts --profile "<私有目录>\fonts.local.json" --cache "<私有缓存目录>"
Set-Location ..
& "<python>" -m localflow --config "<私有目录>\config.local.json" status
& "<python>" -m localflow --config "<私有目录>\config.local.json" catalog
```

必须读 `doctor.json` 的 `all_dependencies_available` 及各模块结果；不要仅以进程退出码判定依赖完整。首次使用在隔离的测试作者目录执行一次 probe → render → 实际 PDF 核对 → review → publish。核对 Word 图号、原图内容、标注归属、连线、字体和留白。排版交付还需由负责排版的人执行目标 InDesign 版本实际置入；需要印刷认证时再走印前流程。新机检查未完成前不要覆盖正式成品。

命令和证据字段见 [localflow 使用说明](../portable-production/localflow/README.md)。`accept` 仅在用户明确终审通过后登记。

## 升级与回滚

1. 暂停当前写入任务，记录运行版本、外置配置与状态目录。保留旧程序目录，并对外置状态做可恢复快照；同步盘不双机共写。
2. 将新包解压到新目录、校验哈希，复用外部配置。先用独立状态和交付副本验证，不原地混合两个版本文件。
3. 新样本通过后切换启动入口到新版本。此版支持源码的 `direct-pdf` 和既有安装的 `engine` 两种布局；同一根下发现两套引擎会阻断，防止混版。
4. 回滚时停止新写入、把入口切回旧程序。若新版本已写入状态或成品，必须同时核对对应状态快照和发布备份，不能只切程序就假定生产状态已回退。已终审成品不得自动覆盖。

本次发布不修改本机正在使用的 `runtime/current`，不迁移生产台账；本机可继续原入口制作。

## 工作台与 Adobe 兼容路线

完整源码保留 `workbench/`、`production-runtime/`、`adobe/`、`collaboration/`。需要 Node.js（本次检查使用 Node 24）、合法 Adobe 安装和包外 machine 配置。参照 `collaboration/machine-config.example.json`：

```powershell
node collaboration/scripts/install.mjs --config "<machine.json>"
node collaboration/scripts/start-workbench.mjs --config "<machine.json>"
node collaboration/scripts/run.mjs --config "<machine.json>" status <JOB>
```

`install` 默认预检；确认迁移范围后才用 `--apply`，保留原工具和失败回滚。运行中 Adobe 会话串行使用。不要将便携路线的 `config.example.json` 传给旧工作台安装器，两者是不同契约。

## 维护者复现发布

先运行对应测试并记录真实结果，再密封。待发布文件须已纳入 Git；生成包必须位于仓库外，输出文件若已存在将拒绝覆盖。

```powershell
node collaboration/scripts/seal-release.mjs <版本ID> <验证记录.json> released
python scripts/release_bundle.py build --root . --output "<仓库外>\版本-portable.zip"
```

对解压包执行 `verify`、CLI 启动、依赖检查和样本流程。验收之后提交代码与密封清单，等待 CI 通过，合并并创建同提交的 tag 和 Release，再上传 ZIP 与校验和。重复打包相同输入应得到相同 SHA256。发布文件修改后应发新版本，不覆盖旧 Release 中同名资产。
