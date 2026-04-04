"""可选第三方依赖探测与回退模块。"""

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
