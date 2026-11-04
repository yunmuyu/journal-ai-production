# 分区与横向布局公共生成接口

region_layout.horizontal_band根据内容实测宽度、最低净距及箭头通道计算整排列位。content_region从显式成员包络、留白和标题区生成分区边界；align_region_bottoms保持同组分区底边一致。用于生成时求几何，不能用成图检查替代。

适用条件：语义成员、区域之间连接关系与边界端口必须已确认；当前不是任意原图的自动语义识别器。调用者需用返回的列位重新生成节点、连接和图片端口，不能只移虚线框。

真实使用：outputs/sun1-regions-20261104/build.py从原始附件重新制作孙晨旭图1，最终通过现有统一入口回传。证据为该目录region-generation.json、tests.log、return.json、visible.json。候选待用户终审，15项相关测试通过。
