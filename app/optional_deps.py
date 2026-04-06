"""
可选第三方依赖探测与回退模块。

本模块负责检测项目依赖的第三方库是否可用，
并在库不可用时提供优雅的降级方案。
采用可选依赖模式，确保核心功能不依赖可选扩展。

主要依赖项：
1. PyPDF2 - PDF文档处理
   - 用于AI聊天机器人的知识库PDF解析
   - PDF_SUPPORT标志是否可用
   - 不可用时禁用PDF相关功能

2. httpx - 异步HTTP客户端
   - 用于IP归属地查询
   - 用于远程图片获取
   - HTTPX_SUPPORT标志是否可用
   - 优先使用httpx，性能更好

3. requests - 同步HTTP客户端
   - httpx不可用时的备选方案
   - 提供相同的HTTP功能
   - REQUESTS_SUPPORT标志是否可用

4. markdown - Markdown渲染
   - 用于新闻内容的Markdown格式支持
   - MARKDOWN_SUPPORT标志是否可用
   - 不可用时仅支持HTML格式

5. PIL (Pillow) - 图片处理
   - 用于图片格式转换和优化
   - 用于Hero图片生成多尺寸版本
   - PIL_SUPPORT标志是否可用
   - Image/ImageOps模块和PIL_FEATURES特性检测

使用模式：
try:
    import requests
    REQUESTS_SUPPORT = True
except ImportError:
    requests = None
    REQUESTS_SUPPORT = False

降级策略：
- HTTP客户端：httpx → requests → 禁用远程功能
- 图片处理：PIL → 禁用图片优化功能
- PDF处理：PyPDF2 → 禁用PDF知识库
- Markdown：markdown → 仅支持HTML

作者：元芯传感技术团队
"""

try:
    import PyPDF2

    PDF_SUPPORT = True
except ImportError:
    PyPDF2 = None
    PDF_SUPPORT = False
    print("Warning: PyPDF2 not installed. PDF knowledge base support disabled.")

try:
    import httpx

    HTTPX_SUPPORT = True
except ImportError:
    httpx = None
    HTTPX_SUPPORT = False
    print("Warning: httpx not installed. Using requests instead.")

try:
    import requests

    REQUESTS_SUPPORT = True
except ImportError:
    requests = None
    REQUESTS_SUPPORT = False

try:
    import markdown as md

    MARKDOWN_SUPPORT = True
except ImportError:
    md = None
    MARKDOWN_SUPPORT = False

try:
    from PIL import Image, ImageOps, features as PIL_FEATURES

    PIL_SUPPORT = True
except ImportError:
    PIL_SUPPORT = False
    Image = None
    ImageOps = None
    PIL_FEATURES = None
