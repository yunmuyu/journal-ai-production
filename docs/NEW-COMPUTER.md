# 新电脑迁移：代码与在制资料分开

本次是 `2026.11.04-r46-clean-move` 迁移预览版，不宣称已通过全新电脑生产验收。原机公共源码已整理为独立发布分支；作者素材、批注和候选另存私有包。不要把旧工作目录整棵复制进代码仓库。

## 安装公共工具

Windows 10/11、Node.js 24、Python 3.12。下载本预览版的 portable ZIP 和 SHA256，解压到 `F:\期刊AI工作台\repo`。本次旧数据仍绑定绝对路径，保留这个位置可避免篡改历史来源及验收身份。如果新电脑没有 F 盘，可以在确认 F 盘未占用后，把空的数据目录挂载为 F 盘；不要覆盖已有盘符。

```powershell
Get-FileHash .\journal-ai-production-2026.11.04-r46-clean-move-portable.zip -Algorithm SHA256
python .\scripts\release_bundle.py verify --root .
.\scripts\setup-new-computer.ps1 -Python 'C:\Python312\python.exe' -RuntimeDirectory 'F:\期刊AI工作台\runtime\python'
```

安装脚本只安装现有锁定依赖，不安装 Office、Adobe、字体或 Cairo 的系统 DLL。CairoSVG 导入失败时先补齐可信 Cairo 运行环境；不要改质量门规避。EMF/WMF/PPTX/Word 转换还需要本机安装相应 Office；VSD/VSDX 需要 Visio。常规 JPG 不需要 Photoshop。Adobe 特殊路线仍串行，另按兼容路线安装验证。

商业字体不随代码或迁移包分发。私有包保留字体 profile；在新电脑合法安装相应字体，并核对 profile 的路径、字形名称和字重。

## 恢复私有资料

私有包是内容哈希去重的 `private-data` 目录，附 `MIGRATION-MANIFEST.json`，不要上传公共 GitHub。它保留工作台当前引用的稿件、原图、当前候选、批注、验收记录和必要来源证据；不携带未被引用的实验目录、失败尝试、旧虚拟环境、缓存和凭据。

```powershell
node .\scripts\private-migration.mjs verify 'D:\搬家包\private-data'
node .\scripts\private-migration.mjs restore-original-paths 'D:\搬家包\private-data'
```

恢复程序先校验所有文件，遇到不同内容的同名目标就退出，不覆盖。当前迁移策略恢复原绝对路径（包括少量旧用户目录下仍被引用的文件），不是随意更名搬目录。权限或盘符不满足时先解决路径；不要直接替换全部 JSON 字符串，否则会破坏来源哈希和验收版本。新机安装字体后，用原位置的私有工作台主机脚本接续，而不是用旧十月示例工作台重新初始化。

本地 reviewer/worker token 在导出时清空，首次配置重新生成；GitHub、模型 API 等凭据必须在新电脑单独配置。不要复制原机账号密钥。

```powershell
node .\scripts\configure-local.mjs 'F:\期刊AI工作台\runtime\python\Scripts\python.exe' 'F:\2026年11月\作图\过程资料\november-workbench\fonts.local.json' 'F:\2026年11月\作图\过程资料\november-workbench' 'F:\期刊AI工作台\machine.local.json'
node 'F:\2026年11月\作图\过程资料\november-workbench\server.mjs'
```

配置程序实际加载字体和依赖、计算新引擎签名及 Python/profile 哈希，不复用旧虚拟环境签名。私有案例通过新配置的 `caseIndexPath` 接入现有入口；公共仓库只携带空案例库。没有私有状态时只能测试公共引擎，不能宣称恢复了当前生产工作台。

## 新机验收与继续生产

工作台启动可能需数分钟，等待 HTTP `/data` 就绪，不循环重启。核对搬家清单中的文章、图件数、当前候选 SHA256、批注及终检通过数。任何缺项先记录，不重建台账或把已有通过稿当作待制作。

用一张尚未完成且已有明确方案的图，通过 `workbench/production-runner.mjs` 原入口执行，验证候选可见后再并行。至少五张条件具备时并行，Adobe 单槽；接单到可见争取三分钟。只把工作台可见计作交付，终审由用户决定。

原机基线有 12 项失败、737 项通过，集中在列布局边界和旧测试夹具的场景字段。完整失败摘要见本预览版发布说明。WorkBuddy 重跑指出的混合图灰度、Word 裁区及特殊编码文本仍须专项修复；本次迁移没有把它们标为已解决。新机首次完整交付尚需验收。
