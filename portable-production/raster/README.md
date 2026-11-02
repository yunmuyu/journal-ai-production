# 公共位图制作入口

常规照片、截图与已有明确组合布局的位图，使用本入口灰度、显式裁切、尺寸设置和 JPG 导出。依赖已安装的 Pillow 和标准库，不调用 Photoshop、Illustrator、桌面自动化、网络或模型。执行 Agent 可更换，计划与报告不依赖聊天记忆。

本入口不判断图件应走哪条路线。调用前必须完成原包、Word 图号与内容配对，检查是否有更合适的可编辑/矢量源件，记录保留位图的依据。不能仅凭 PNG 后缀选择本路线。特殊格式或无法由公共解码器可靠处理的输入，报告具体限制后才使用已有原生格式兼容工具；不能把 Photoshop 作为常规 JPG 必经步骤。

从 `portable-production` 目录执行：

```text
python -m raster render <private-plan.json>
```

计划版本1：

```json
{
  "version": 1,
  "inputs": [{"path": "<PRIVATE_ROOT>/source.png", "sha256": "<actual-sha256>", "crop": null}],
  "layout": {"mode": "single", "gap_px": 0},
  "output": "<PRIVATE_WORKSPACE>/author-fig1.jpg",
  "width_mm": 80,
  "target_dpi": null,
  "quality": 95
}
```

- 输入先校验哈希，再正规化 EXIF 方向。`crop` 为正规化后坐标的 `[left, top, right, bottom]` 整数像素边界，或 `null` 保留全幅。不自动找白边、裁内容、拆屏或改变文字/图表数据。
- 单图 `single` 必须只有一个输入、gap为0。组合 `row/column` 按输入顺序横排/纵排；`grid` 另需 `columns`。所有组合使用同尺寸单元格（该组最大原像素宽、高），图像居中白底，不隐式缩放输入。空单元格保留白底，顺序及每图位置写报告。组合方式必须来自已明确的图件内容和布局要求。
- 支持 PNG/JPEG/TIFF/BMP/WEBP/GIF 的单帧图像；多帧拒绝，不悄悄只取第一页。透明区域先合成白底，再灰度。JPEG 为灰度 L 编码，默认质量95（允许90–100），不输出 PDF。
- 可选 `grayscale_weights:[r,g,b]` 为统一RGB通道混合，三个权重须有限、非负且和为1。例如 `[1,0,0]` 使用红通道亮度。省略时仍调用原标准灰度算法，默认JPG字节不变；报告记录实际权重，默认为null。必须根据源图真实颜色采样选择并复核所有类别，不可为了区分某两色而忽略其他颜色撞灰；不能凭此改图形、数据或标签。透明白底合成后才混合，同一计划所有输入使用同一组权重，灰度语义仍需独立核验。
- `width_mm` 必须由上游任务给定。本入口不根据像素字高或 OCR 推断字号，也不自动决定单栏、双栏、重绘或拆图。
- `target_dpi:null` 或省略：保留原像素，按宽度计算 DPI，使用 EXIF 有理数存储，避免 JPEG 整数密度导致物理宽度漂移。源有效分辨率低于300 ppi会报告警示，不能把更高 DPI 数值或插值写成新增细节。
- 显式 `target_dpi`（至少300）才按目标宽度重采样，保持纵横比例（像素取整）。报告同时保留原像素、目标像素、请求DPI、实际DPI、有效源分辨率及 `resampled:true`，不掩盖插值。
- 禁止与任一输入同路径，也禁止覆盖已有 JPG、同名预览或报告。新尝试使用新目录，源件前后再次核对哈希。失败可能留有未完整的候选，不能当成功回传。

成功 stdout 为 JSON（status=candidate），输出 JPG、从实际 JPG 解码的同名 PNG，以及 `.raster.json` 加工报告；文件引用均含 SHA256。失败 exit1，stdout包含错误，不自动重试或改变处理范围。

报告不是验收。回传前调用公共 `task_quality` 的 precheck/postcheck/finalize/verify，独立核验来源、实际格式、像素、DPI、尺寸、灰度及源/产物预览。独立审阅仍需看内容是否完整、关键文字是否可辨、灰度是否丢失分类含义；不测图片内字号不等于取消质量检查。候选回到工作台待用户终审，不直接覆盖批准交付。

验证：`python -m pytest tests-raster -q`。合成用例覆盖真实 CLI、源哈希、格式、显式裁切边界、灰度、alpha、EXIF、组合顺序、默认不重采样和显式插值记录。真实作者案例由本机任务留存证据，不进入仓库；特殊格式、复杂色彩配置和超大多帧未声明已验证。
