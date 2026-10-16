# Agent填写review的最小职责

- snapshot：逐文件sha256必须与probe完全一致；源改变后重做受影响身份/内容判断。
- identity：Word资产ID、当前完整图号、核对方法与证据页。只看文件名/尺寸不能置verified=true。
- sources / selected_primary：原附件、Word媒体、候选加工源分别记录；不把有源PDF自动认成矢量，不把PNG认成原始高清拍摄。
- export：整体/拆分、PDF数量、子图标签和内部面板数量分别记录；缺字母不是整体一张的证据。
- route / capability：图种、实际可用的加工方式和该适配器支持状态分开。保留图形、重排文字、原生重建都有边界。
- protection：曲线、面板、拓扑、色彩、图例系列含义。无可靠原始数据不能推算并重建曲线。图例遮住的数据不能补画。
- layout：推荐栏宽与confirmed_column/locked分离。8pt优先，容量未测时写false。
- issues：对象/图号、原证据、范围、阻塞层级和待核问题；不得先自动纠错再当来源。
- rules：标required/not_run/not_applicable或pending，不能把挂载规则写成通过。
- ready_next_step：可独立推进的提取/重排任务；内容疑点只阻断受影响定稿，不停止整批可做的准备。

只要本地历史记录、同图已确认修改、源配对或生产实测缺失，正式准入仍不得被自动标为完成。自动化等级是建议展示字段，不是独立的授权或发布开关。

实际路由CLI必须提供当前输入清单重新核对原文件哈希；仅旧probe与旧review相互一致不算当前源核实。Python API不传manifest时单列live_source_snapshot待核，不能正式下发。桥接保留同一建议的历史，冲突栏宽另加门禁，不改原确认值。
