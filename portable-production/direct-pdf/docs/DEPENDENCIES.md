# 依赖和许可边界

本次验证环境版本锁定在 requirements.txt；不声称它们是最新版本。Windows 尚未执行实机安装与运行，首次安装脚本不是已验证的本机运行结果。

CairoSVG 的官方安装文档指出 Windows 需要 Cairo（例如通过 GTK）及相应构建环境；具体是否需要编译取决于采用的预编译依赖。先用 doctor 判断 Cairo DLL 能否加载，再由本机 Agent 根据现有环境选择配置方式，不自动安装陌生 DLL，不设置全系统 PATH。官方说明：
https://cairosvg.org/documentation/index.html

SVG 路线保留 CairoSVG 作为矢量转换器。本次验证发现已安装 PyMuPDF 版本直接转换某些 SVG 会遗漏 CSS 虚线设置，故没有采用其 SVG 转换作为静默替代。该缺陷不影响本引擎用 PyMuPDF 绘制自有矢量文字与几何；已加入 SVG 虚线保留回归。

PyMuPDF/MuPDF 提供 AGPL 与商业许可两种路线。源码开放、分发、服务部署或后续商业化应按实际用途核对许可，不把“有 Python 包”理解为无许可约束。参考：
https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright
https://pymupdf.io/licensing

本包不重新许可第三方依赖，也不转移字体授权。宋体、汉仪中宋简、Times New Roman 从用户本机配置；字体嵌入标志被检查，但这个技术检查不替代实际使用授权。

不要把作者原稿、原始/候选 PDF、字体缓存、绝对机器路径配置上传 GitHub。完整本机包包含真实作者材料，仅供本机测试；源码净包不包含它们。
