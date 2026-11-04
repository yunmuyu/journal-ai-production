# 完整诊断、生成连接与混合联动布局

本补丁复用现有 Scene、字体测量、BoundaryGeometry、region_layout、Assets 和 production-runner，不新增生产执行器。

## 完整诊断

runner 的失败状态新增 `diagnostic`：`code`、`message`、完整 `issues` 和原始结构化 `detail`。命令行杂项警告不会替代 JSON 错误；完整 stdout/stderr 仍保存在原 `failure.log`。

框尺寸和箭头长度继续报告实际值/期望值。明确 side/fraction 的错误端口新增 `expected_point` 与 `delta_pt`；只给节点名时列出四侧候选点，不能把建议点冒充已确认方向。多条独立自动生成连接会先统一验证，一次返回全部生成约束问题，验证通过才加入场景。

## 生成时计算端口与箭头空间

```json
{
  "nodes": [{"id":"a","text":"输入"},{"id":"b","text":"输出"}],
  "measured_groups": [{"id":"row","nodes":["a","b"],"axis":"row","origin":[10,10]}],
  "connections": [{"id":"ab","from":"a","to":"b","from_port":"right","to_port":"left","arrow":true,"auto_route":true}]
}
```

- `auto_route:true` 使用公共边界函数计算端点；`from_fraction/to_fraction` 默认0.5，椭圆及菱形使用真实方程，矩形使用边长比例。
- 圆角、终止和输入输出框目前只支持已验证的四侧中点；其他比例明确拒绝，不以外接矩形猜边界。
- 同一测量行列的相邻框如有生成连接，会先预留箭头空间再定位置。标准箭头末段保持最终3mm，6、7.5、8pt均已验证；双向箭头预留两端。
- 已确认的正对端口支持直线或正交折线；复杂绕线仍需明确路径。通道不足报告实际值、所需值、差值，不猜测绕线或改变源/目标。
- 旧的原图路径不自动改写。显式 `paths[].auto_terminal` 复用相同末段计算，标准箭头不再随设计字号缩短。

## 图片、文字、容器与连接共同排版

在原有 `scene` 规格中声明成员，资产由既有入口加载后执行：

```json
{
  "mixed_layout": [{
    "id":"panels", "axis":"row", "origin":[10,10], "align_bottoms":true,
    "groups":[
      {"container":"left","nodes":["a"],"texts":["title-a"],"assets":["photo-a"]},
      {"container":"right","nodes":["b"],"texts":["title-b"],"assets":["photo-b"]}
    ]
  }]
}
```

- 复用公共分区排布，默认组净距6pt；箭头通道需要更多空间时按真实端点和组内留白计算，不能固定压成6pt。
- 节点 owner 文字随节点自动加入；分区内其他文字和图片必须明确归属。未绑定、重复绑定或成员越界都具体列出，不能把图片留在旧位置。
- 图片只平移，源文件、裁区、像素尺寸和比例不变；容器、节点、文字与已确认内部路径使用相同位移。跨组生成连接重新计算端口及末段，源/目标不变。
- 内部手工路径放在组的 `paths` 中；跨组手工直线必须有明确端口声明。未确认的复杂跨组绕线返回具体路径ID，不擅自更换路线。
- `fit_container:true` 可按已绑定内容求分区边界；默认保留原分区尺寸。`align_bottoms:true` 仅用于明确并列组，复用公共底边对齐。
- 完成后收紧画板右下空白，保留原有安全余量；绑定页面外部端口时不改变画板。
- 新碰撞、端口错误或缺绑定时整次回滚，包括图片位置和画板尺寸；不返回半移动场景。最终仍运行原场景及实际PDF检查。

## 调用与生产

继续使用原 production-runner 和主配置。新制作方案可使用上述声明；旧作者脚本不会因为工具升级自动变成声明式方案。已有候选先核对复用，工具验证稿不自动登记工作台或终审通过。

合成混合图证据：`evidence/mixed-smoke/`；它只验证公共几何/像素链，不代表任何作者图的语义已核对。
