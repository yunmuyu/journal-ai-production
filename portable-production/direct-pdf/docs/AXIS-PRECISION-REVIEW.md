# 字号与同轴刻度复核

输出报告对最终基础字号低于 8 pt 的图给出 `base_font_below_8_requires_review`；对无基线偏移的局部缩字另给 `reduced_nonscript_text_requires_review`，要求核对该图的明确例外。带基线偏移的数学上下标不自动当作普通文字缩字；是否真为上下标仍需人工核实。它不自动证明图内位图文字的字号。

`chart` 按 x、y 轴分别检查十进制刻度。当至少两个刻度带小数、同轴显示的小数位不一致时，报告 `axis_decimal_precision_mismatch`，例如 `0, 0.2, 0.4, 1`。这是复核提示，不自动改写数值，也不将单位、科学记数法或类别名猜成普通小数。

自由 `scene` 需要显式按轴分组：

```json
"axis_tick_groups": [{"id": "y", "text_ids": ["y0", "y1", "y2", "y3"]}]
```

分组只引用 `axis-tick` 文字；错误或重复引用会拒绝。未分组的刻度报告 `axis_tick_group_missing`，不能宣称已检查同轴精度。字号或刻度提示存在时，PDF 仍可作为候选查看，但报告状态为 `candidate-editorial-review`、`overall_checks_passed=false`，不能当作全部检查通过；需人工按原稿和用户要求复核。

交付文件应先在质量门禁的契约中逐图列出目标文件名及 PDF 或 JPG 格式，交付前核对实际文件集；不因为可以生成两种格式就同时交两种。图中数学上、下标为语义字号，不等同于基础字号。
