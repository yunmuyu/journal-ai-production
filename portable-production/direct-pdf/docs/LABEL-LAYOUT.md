# 公共文字测量与生成

`scene`、`Scene.box`、`Scene.text` 共用 `label_layout.layout_label`。不要在作者脚本复制字体测量、竖排字列、换行算法或椭圆试算。

## 用现有 scene 入口

```json
{
  "nodes": [
    {"id": "input", "text": "数据采集模块", "wrap_width_pt": 32},
    {"id": "monitor", "text": "系统监控", "vertical_text": true}
  ],
  "measured_groups": [
    {"id": "row", "nodes": ["input", "monitor"], "axis": "row", "origin": [15, 15]}
  ]
}
```

- `wrap_width_pt` 是 8 pt 设计时的文字墨迹限宽，框内留白另加；随设计字号同比变化。它与 `wrap_chars` 互斥。
- 先按已有 ICU 中文词边界和完整英文/数字标识分词，再用 FontRegistry 的实际宽度换行。完整词超过限宽返回 `label_word_too_wide`，包含词和实测宽度；调用者调整布局，不拆标识或自动缩字。
- `vertical_text` 直接复用公共竖排，测量、生成、审计和 PDF 使用同一文字对象；中文正排，英文按已有混排规则处理。不要把 VR 拆成 V、R 两个框内字。
- `measured_groups` 先测量实际换行/竖排文字，再生成框和行列。默认框净距 3 pt；分区净距使用公共 `region_layout.horizontal_band` 的 6 pt 默认。连接、标签、箭头另留通道，不能硬套无连线框距。
- `Scene.box(..., kind='ellipse')` 未指定宽高时，用包住带留白文字矩形的最小面积同轴椭圆尺寸；原有明确尺寸不自动改变，仍须通过边界检查。

## 区域与连接

直接复用 [REGION-LAYOUT.md](REGION-LAYOUT.md) 的 `horizontal_band`、`content_region`、`align_region_bottoms`；语义成员和端口确认后，按返回的列位重新生成框、文字、连线及图片位置。仅写 `region-generation.json` 不会自动启用排版。

本功能负责已确认内容的几何生成，不识别任意原图的正确拓扑，不授权合并反向箭头、替换图标或改动数据。已有候选先复用；工具更新不触发重做或自动终审。
