# v0.2.0rc1 变更

新增：ingest_geometry.py、ingest_native.py、agent_spec.py、agent_entry.py、graph_layout.py、rules_registry.py；Node薄桥接、文件协议、精简Agent证据、测试。

修改：charts.py新增经过安全核对的图外上方图例版位；layouts.py注册通用语义图；cli.py增加agent入口；__main__.py增加主入口保护；doctor增加图像候选依赖；版本及requirements。

复用：轴单位、三位分组、文字测量、字体缓存、菱形校准、框内留白、整图适配、Arrow5、最终0.5pt可见矢量描边、墨迹裁边、实际PDF检查及逐页汇总。不是重新审查或覆盖仓库规范。

先前资料里“自动入图前端尚未实现”对v0.1.2.1有效；本轮已实现受控范围的前端，不能外推成所有图种都可自动处理。详见CAPABILITIES.json。

测试旧素材的回复是开发夹具，不是新图盲测证据。未来新图不能拿夹具答案代替Agent读图。
