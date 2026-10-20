# 可选 task quality gate（MVP）

这是生产 CLI 外的一层证据门禁。它不制作图、不发布文件、不改变 localflow 默认行为。依赖已有 PyMuPDF、Pillow 和 Python 标准库；哈希、安全子路径与写锁复用 `localflow.core`。没有新增安装依赖。

从 `portable-production` 目录调用同一个已验证的 Python：

```text
python -m task_quality precheck <contract.json>
python -m task_quality postcheck <contract.json> <submission.json>
python -m task_quality finalize <contract.json> <review.json>
python -m task_quality verify <contract.json>
```

所有命令 stdout 为 JSON，失败 exit 1，含 `error.code/detail`；exit 0 只表示当前阶段成功。precheck 是 prechecked，postcheck 永远是 candidate + manual pending，finalize 是 reviewed，verify 是 verified。没有 ready/accepted/发布操作。未知字段、重复 JSON 键、NaN、未知机械检查、空人工项目均拒绝。

## 契约与最小调用

[contract.example.json](contract.example.json) 仅含占位路径与零哈希，不能直接生产。所有 FileRef 均为 `{path, sha256}`，路径必须指向实际私有文件；sha256 为小写64位。主 `source` 必须是可生成单页预览的 PDF/JPG/PNG；完整 Word、PPTX、多附件和原图逐项列入非空 `source_inputs`，不要只登记提取图。不能由门禁推断未登记附件。

`route` 只接受 diagram/circuit/source-preserving-chart/raster；data-redraw 拒绝。允许保留原图的统计图，不依据backend名称禁用。所有 route 最低人工项：source_content、visual、runtime_provenance；diagram/circuit 另需 topology、label_ownership。`allowed_changes` 和 `immutable_content` 是审阅约束声明，门禁不声称能自动证明标签或几何语义未改变。

history 的 `evidence` 指向历史检索完成回执，内容必须严格包含：

```json
{"checked":true,"conclusion":"new","reusable":false,"observation":"已按文章、图号和当前来源检索，未发现可复用结果；真实报告位置写在此处"}
```

契约 history 的 conclusion/reusable 必须与回执一致。未查拒绝；已有可复用输出而计划新制，必须有非空具体 revision_authorization。conclusion=reuse 拒绝新制候选，请走现有复用流程。这里是可审计声明，不能证明执行者确实完成历史检索；独立审阅须查实际证据。

`frozen_manifest` 指向现有权威数组清单，门禁保留整份清单hash，只投影每项 path/sha256 校验字节，其余历史metadata不解释。每个 output 的 delivery_target 仅用于只读身份/CAS核对，必须在 author_roots 下且不与workspace重叠。任何目标在冻结清单内都拒绝新制；正式修订沿用现有专门流程。冻结目标不会因这个契约中的修订文字而解锁。

专属 workspace 与全部作者根目录、登记输入必须隔离。workspace的独占标记用exclusive create；同task同contract可恢复，其他身份及嵌套已占workspace拒绝。只读封存envelope绑定contract、来源、冻结清单、runtime文件及实际gate模块字节。输出相对路径不得越界、重名或进入gate状态目录。

runtime.python必须等于实际sys.executable且hash一致。code_root/code只能证明指定代码文件未变，**不能证明生产者当时导入了该代码**；runtime_provenance人工项须引用已有check_candidate/engine_signature或实际module.__file__证据。font_profile同样只证明配置身份，不能自动证明最终PDF全部用了该字体。gate自身实际模块与localflow.core文件hash自动加入envelope。

failure_policy声明最多1–3次语义尝试、local-only修复，预算未知为null。门禁不执行自动重试，也不计算未提供的人时/费用；由现有调用流程消费policy。

## 后检及审阅回执

submission严格包含artifacts(FileRef数组)与audit(FileRef)。实际workspace PDF/JPG集合必须精确匹配outputs。PDF实测单页、物理宽度；可选stroke_pt检查PyMuPDF识别的有色、非全透明且与页面相交矢量路径，容差±0.005 pt。填0.5可挡住0.510337等描边。统计曲线不适用统一线宽时显式填null，仍需人工核验。此检查不是完整PDF可见性/裁剪/遮挡引擎，嵌套图与特殊PDF结构仍要看预览。

JPG实测实际格式、像素、DPI和物理宽度。物理宽度容差0.05mm；DPI容差0.5。每个产物及主source都由gate从当前字节重新生成PNG预览，不消费执行者自带截图。预览输出在workspace/.task-quality。

audit是包装现有报告的薄回执（不得伪造既有报告内容）：

```json
{
  "output_bindings":{"fig1":"<actual-artifact-sha256>"},
  "coverage":[{"id":"dimensions","status":"checked","evidence":[{"path":"<actual-report>","sha256":"<hash>"}]}],
  "source_geometry":{"status":"pending","evidence":[{"path":"<source-or-report>","sha256":"<hash>"}],"observation":"源框尚未导入Scene"},
  "label_path_binding":{"status":"pending","evidence":[{"path":"<source-or-report>","sha256":"<hash>"}],"observation":"标签未绑定实际owner/path"},
  "scene":null
}
```

output_bindings必须精确匹配每个实际output ID→产物SHA；另一张图同尺寸/线宽的报告也不能混用。coverage必须覆盖契约每个mechanical ID，状态仅checked/pending/not-applicable，每项必须引用存在且hash相符的具体证据文件。支持mechanical ID：dimensions、coverage、pixels、dpi、stroke、artifact_set、preview_hashes。必需检查不可任意not-applicable；pixels/dpi仅纯PDF可NA，stroke仅未要求stroke_pt可NA。机器测量始终自己运行，不相信报告的“通过”。

scene为既有Scene.export JSON的FileRef或null。diagram/circuit缺scene，或源PDF存在矢量而scene无nodes，或texts缺owner/owner未绑定nodes或paths，保留pending。diagram/circuit的源几何/标签归属不可NA。source-preserving-chart/raster可有理由地NA；此声明仍由独立reviewer核实。即使Scene结构检查过，也不自动证明电路连接、统计值、公式或文字语义正确。必需机械检查pending不能finalize。语义pending可由独立reviewer显式结案：source_geometry对应source_content，label_path_binding对应diagram/circuit的label_ownership（其他route为source_content），route_semantic_coverage对应topology；对应项须approved、有具体观察且引用主source文件hash及全部source/产物预览hash。receipt保留automatic_coverage_pending原状及manual_resolutions，不把人工结论改写为自动checked。未知自定义语义pending要求同名manual条目。

review严格包含reviewer、candidate_sha256、items。每条items为id/decision/observation/evidence；全部manual_review逐项approved，具体观察不能为空，evidence列出已绑定的SHA值。所有source/产物预览hash都必须在人工项证据引用中出现。producer与reviewer比较时忽略大小写和首尾空格；同人、缺项、pending/rejected、错hash或审阅后变更都拒绝；机器未覆盖语义须按上一段逐项解决。

finalize封存只读receipt，绑定contract、envelope、sources、产物、预览、audit和audit附属证据；verify重新计算全部hash、冻结清单及delivery target状态，并重验review完整性。receipt是可审计的审阅声明，**不是密码学身份认证，也不是确实看过图或视觉真实性的证明**。同权限进程仍能绕开工具修改作者文件、重写只读文件或伪造身份；这里没有OS沙箱/权限隔离承诺。

## 接入与回滚

在现有localflow.review之前，先verify成功，把receipt的path/hash作为现有review evidence。紧贴localflow.publish前再verify；继续使用原有check_snapshot、check_candidate、目标旧hash、冻结和writer lock保护。Python调用方也可直接调用task_quality.gate.verify。receipt不替代localflow的任何来源、候选、替换或用户终审门禁；MVP不会自动接入已发布CLI。verify与外部publish间仍有时间窗口，调用者应保持现有写锁/CAS保护。

失败按error.code只修具体项；封存记录不覆盖。新尝试使用新task id/workspace；相同契约恢复只接受相同已封存字节。不要清理真实证据来让失败变通过。回滚只需停用这四个可选命令并撤销新增task_quality与tests-task代码；未改生产CLI/作者资料/release配置，无发布物需回滚。

## 已知验证边界

合成真PDF/JPG测试见tests-task/test_gate.py，覆盖错源、旧历史复用、独占冲突、冻结目标新制、缺产物、错误宽度/描边、coverage缺项、Scene假零/owner缺失、自审/待审、来源/产物/预览/报告/冻结字节变化、多附件与合法闭环再verify。静态检查器ruff/basedpyright本环境未安装，未声称通过。真实作者样本与本机绝对路径不得进入Git。
