# 新电脑接续生产

公共工具以 GitHub main 和最新正式 Release 为准。日常入口只有仓库根目录的 `journal.mjs`；内部模块、历史实验和旧数据目录的 server.mjs 都不是另一套生产入口。

## 1. 安装工具和运行环境

使用 Windows 10/11、Node.js 24、Python 3.12。将 `journal-ai-production.zip` 解压，内部仓库目录放到 `F:\期刊AI工作台\repo`。私有资料保留历史绝对路径；新机须具备 F 盘及这些目录的写入权限，不直接批量替换 JSON 路径。

```powershell
Get-FileHash .\journal-ai-production.zip -Algorithm SHA256
Set-Location 'F:\期刊AI工作台\repo'
python .\scripts\release_bundle.py verify --root .
.\scripts\setup-new-computer.ps1 -Python 'C:\Python312\python.exe' -RuntimeDirectory 'F:\期刊AI工作台\runtime\python'
```

安装使用同一份锁定依赖。CairoSVG 需要 Cairo 原生运行库；Office 转换需要相应 Office，VSD/VSDX 需要 Visio。普通 JPG 无需 Photoshop；Adobe 特殊路线仍单槽。商业应用与商业字体不随包分发，须在新机合法安装。字体 profile 只记录路径，不含字体文件。

## 2. 恢复私有资料

`journal-production-data.zip` 只在两台电脑之间传递，**不要上传公共 GitHub**。解压得到 `private-data`，含去重文件和 MIGRATION-MANIFEST.json。

```powershell
node .\scripts\private-migration.mjs verify 'D:\搬家包\private-data'
node .\scripts\private-migration.mjs restore-original-paths 'D:\搬家包\private-data'
```

恢复先校验全部文件；遇到不同内容的同名目标就停止，绝不覆盖。包保留原稿、源图、当前候选、批注、验收、发布回执及可复用方案；不迁移旧虚拟环境、实验引擎、私有工作台代码和无引用失败目录。当前证据引用的历史文件仍保留，不按年龄删除。

## 3. 绑定并启动唯一入口

安装字体后核对 fonts.local.json。workspace-roots.json 记录稿件根目录。本地 token 导出时清空，配置时自动重建；账号/API 密钥在新机单独配置。

```powershell
node .\journal.mjs configure --python 'F:\期刊AI工作台\runtime\python\Scripts\python.exe' --fonts 'F:\2026年11月\作图\过程资料\november-workbench\fonts.local.json' --data 'F:\2026年11月\作图\过程资料\november-workbench' --config 'F:\期刊AI工作台\machine.local.json'
node .\journal.mjs doctor --config 'F:\期刊AI工作台\machine.local.json'
node .\journal.mjs start --config 'F:\期刊AI工作台\machine.local.json'
```

默认工作台 http://127.0.0.1:18741。首次恢复需要数分钟，等 /data 就绪，不循环重启。关闭此终端进程即可停止，再用同一 start 接续。需要更新现有配置时 configure 加 `--refresh`，不复制旧引擎签名。

## 4. 验收和继续制作

```powershell
node .\journal.mjs status --config 'F:\期刊AI工作台\machine.local.json'
node .\journal.mjs produce --config 'F:\期刊AI工作台\machine.local.json' --request 'D:\任务\request.json'
```

request.json 沿用统一 production-runner 契约，不新增执行器。核对搬家清单的文章、图件、输出哈希、批注和终审状态；已有通过稿不重做。至少五张条件具备时并行，接单到可见争取三分钟，必要检查保留，终审由用户完成。

本版在原机隔离数据目录验证工作台恢复，并以真实 PDF 和 HTTP 工作台验证并行加工回传；不等于已在另一台实体电脑验收。新机仍须通过依赖、字体、资料和一张真实任务验证。缺少语义绑定的图件不会因迁移自动变为可执行。
