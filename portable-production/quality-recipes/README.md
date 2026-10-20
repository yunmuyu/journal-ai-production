# 实测 Scene 关系检查（可选）

`node diagram-relations.mjs measured-scene.json recipe.json`

输入必须是公共生成器真实测字后的 Scene（或含 scene 字段的诊断），不是手填预期坐标。配方 rules 显式指定该图需要验证的对象关系；检查失败或结构缺失 exit 1，通过 exit 0。输出绑定 Scene 和配方字节哈希，无绘图或发布能力。

支持：

- horizontal_gap：left/right节点及minimum_pt；同一横排需y投影重叠，净距扣除两框半描边。
- vertical_path：path全体点同x；允许同轴箭头终端点。
- label_left_corridor：label墨迹位于upper_node底边与lower_frame顶边之间，位于指定path唯一覆盖字形y范围的竖段左侧；minimum_pt/maximum_pt限定贴近距离。

配方中的路径归属、分组及阈值由主代理对照用户规则和源图决定。这只能验证声明的几何关系，不能自动理解图意，不能证明 Scene 与最终 PDF 一致。最终 PDF 的框线、实际文字和源图关系须另行核对；独立复核仍不得省略。

首个真实负例为邓图3两个源框几何距0.80859375pt、可见净距0.30859375pt，被本检查以exit1拒绝。源资料和具体配方留在项目私有work目录，不打包进代码。适用范围尚未经过其它图类推广验证。

回滚：停用该检查及委派文档中的配方要求即可；未改既有Scene绘图器、活动配置或正式CLI。
