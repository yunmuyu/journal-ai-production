# 候选判断的本地边界

protectDecision(raw, local)不调用模型、不写状态。local仅来自核实的本地记录：constraints含confirmed和evidence，originalMarks是原始题注逐字证据，regions是内部区域，fit仅接收本机实测记录。model输出不可写入这些输入。返回原始建议、受保护结果和具体冲突，始终publishable=false，必须由现有审核流程决定采用。

栏宽待实排不降级加工路线。未知图源阻断后续建议；视觉分区不能授权拆分；交付集合完整且无重复。所有模型调用仍为可选实验，不改变production-runtime或正式工作台。

验证：node --test knowledge/decision-boundary.test.mjs。真实作者与响应保留在外部work目录，不入Git。
