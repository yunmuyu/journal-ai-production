# 期刊图件前置筛选 v2 / 0.2.0 候选

现有对话/Agent入口的只读证据提取与生产路由。不是新上传网站，不是正式PDF制作器，不自动替换production-runtime。

```sh
cd candidates/agent-preflight-v2
python -m pip install -e '.[test]'
python -m journal_preflight probe input-manifest.json --out candidate-probe
# Agent查看原稿和证据后填写review.json；不是让用户量坐标。
python -m journal_preflight route candidate-probe/probe.json review.json --manifest input-manifest.json --out screening.json
python -m journal_preflight bridge legacy.json screening.json --out merged-candidate.json
python -m pytest -q
```

输入示例（绝对路径或相对于当前工作目录）：
```json
{"files":[{"id":"paper-a","path":"/data/paper.docx"},{"id":"source-a","path":"/data/figure.svg"}]}
```

支持DOCX正文图片与相邻图题、PDF实际文字/矢量计数/图像对象、SVG和draw.io原生元数据、单帧PNG/JPG/TIFF/WebP探查。PPTX、任意Office对象和任意截图自动识字未实现；不猜测拓扑、不OCR、不扫描字体、不调用Adobe或外部模型。

源文件只读；现有输出不覆盖。匹配候选不直接确认为Word身份。路由时重新核对当前原文件hash，不能拿两个过期JSON相互一致冒充当前源核实。Python API省略manifest时单列待核，不能正式下发。

Word图号、源版本、完整交付范围、同图已确认修改和已确认栏宽仍为硬约束。照片/热图不按图种一律判D；保护需求与保彩批准分开。只有PDF必交，不以缺.ai阻塞直接PDF路线。默认8pt、6pt下限及现行整图适配规则保留；栏宽建议不是容量通过。

桥接只向aiProposal.preflightV2追加候选，保留旧建议历史、productionDecision、caseRetrieval、userCorrectionContext和验收。仅显式相同ID匹配，旧确认栏宽冲突另加门禁。正式接入仍需本机权威记录和现有prepare-decisions，不能跳过案例与纠正检索。

本候选33项合成专项测试通过（Linux容器）。不是GitHub全仓回归、Windows/Adobe原生测试或正式出版验收；ready_for_publication始终false。作者原稿、图件、正文、字体、缓存、机器配置及样图报告不入本目录。依赖适用各自许可证。详见docs/INTEGRATION.md。
