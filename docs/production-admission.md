# 生产准入和共享故障

沿用production-runner与raster-batch，production-admission.mjs仅提供共同准入检查，不是另一套执行器。生产配置指向同一knownFaultsFile；省略该字段时自动读取workbenchRoot下的production-known-faults.json。主线程是登记文件的唯一写入者，子代理交判断与证据，不能自行解除挂起。

每条故障含id、open/resolved状态、engineSignature、scope、reason、证据path/SHA。版本为null表示用户明确挂起或与引擎无关的入口限制；技术缺陷绑定实际冻结签名。scope可按图件、来源SHA、方案SHA、加工操作、方法和输出数量匹配；多个条件同时满足才拦截。不能按作者名字或一次未知错误封禁整条路线。

入口每次派发重新读取登记文件；匹配且证据哈希有效时在开工具/建服务任务前返回known_fault。实际运行已回传的同一候选允许复核可见性，不算再次制作。已完成项不因其他图的挂起阻塞。

参数/布局问题以specHashes精确限制失败方案，action=correct_plan；更正方案后可进入原有检查，不得称为全局能力缺陷。源格式/公共工具缺陷用来源或操作及版本限定，action=wait_for_verified_fix；不得换Agent反复重试。resolved必须有已经验证的修补记录，由协调者修改，保留原证据。

buildProductionQueue(config,plans,rows)以实时/data为准，输出ready/reused/held。候选待终审、用户已通过的图复用；无计划、版本过期、来源/历史证据变化、输出集合缺失、已知故障分别说明。它是派发前结构和来源检查，不冒充渲染/内容审核；实际布局、字体、灰度等继续由固定引擎与回传检查执行。已知离线失败必须先登记，不能只写在代理汇报中。

派发的并发额度与实际并发分开报告。当前PDF额度6，实测回归6路渲染重叠；真实首批复用2个已有PDF、2路检查、2张新增可见回执。没有持续一小时产量结论。Adobe仍单槽；未验证路线单独挂起。

工作台重启恢复已发布候选时，accepted:false不是“删除候选”。仅在候选文件SHA、输出集合和记录版本完全匹配时恢复显示，仍保持未通过；不同版本、文件变化不得覆盖。

主入口将原包和Word路径绑定到服务端批次目录的规范写法，先验证真实路径、SHA与文章身份，再调整路径字符串；不得把相同字节的其他文件偷偷替代原件。Windows正反斜杠或已核对的路径别名不再造成提交冲突。成功接续后清除当前error/failure显示，历史失败仍留在failures中。
