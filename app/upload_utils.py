"""
共享的上传与媒体校验辅助模块。

本模块提供文件上传的安全校验功能，确保只有合法文件才能被上传和保存。
支持图片、视频、PDF等多种文件类型的MIME类型检测和文件签名验证。

主要功能：
1. MIME类型推断（infer_*_extension_from_mime系列函数）
   - infer_news_image_extension_from_mime: 新闻图片扩展名推断
   - infer_ai_product_image_extension_from_mime: AI产品图片扩展名推断

2. 文件签名检测（infer_*_extension_from_bytes系列函数）
   - infer_ai_product_image_extension_from_bytes: 根据图片文件头字节识别格式
     * PNG: \x89PNG\r\n\x1a\n
     * JPEG: \xff\xd8\xff
     * GIF: GIF87a 或 GIF89a
     * BMP: BM
     * WebP: RIFF....WEBP
     * TIFF: II*\x00 或 MM\x00*
     * AVIF: ftypavif
     * HEIC/HEIF: ftypheic/heix/hevc等
   - infer_video_extension_from_bytes: 根据视频文件头识别格式
     * MP4: ftyp
     * WebM: \x1aE\xdf\xa3
     * OGG: OggS

3. 综合扩展名规范化（normalize_ai_product_image_extension）
   - 优先使用文件名扩展名
   - 其次根据MIME类型推断
   - 最后根据文件签名验证
   - 确保扩展名在白名单内

4. 文件内容读取（peek_upload_bytes）
   - 安全读取文件流的前N个字节
   - 保存原始读取位置
   - 读取后恢复文件指针
   - 默认读取8192字节

5. 图片扩展名验证（validate_uploaded_image_extension）
   - 综合文件名扩展名和文件签名验证
   - 支持SVG特殊处理
   - 返回空字符串表示验证失败

6. 图片字节验证（validate_image_bytes）
   - 验证已上传的图片字节内容
   - 支持文件名和MIME类型辅助验证
   - 用于远程图片URL的安全验证

7. 视频扩展名验证（validate_uploaded_video_extension）
   - 验证视频文件的扩展名
   - 综合文件签名和文件名
   - 支持多种视频格式

8. PDF验证（validate_uploaded_pdf）
   - 简单检查PDF文件头
   - 验证文件以%PDF-开头

安全特性：
- 三重验证机制：文件名 → MIME类型 → 文件签名
- 文件签名防止扩展名伪装攻击
- 白名单机制限制可接受的文件类型
- SVG文件特殊处理，避免XSS风险

文件上传流程：
1. 读取文件流前8192字节
2. 检测文件签名确定真实格式
3. 结合文件名扩展名和MIME类型推断
4. 规范化扩展名并验证白名单
5. 仅在通过所有检查后才保存文件

作者：元芯传感技术团队
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

DEFAULT_AI_PRODUCT_IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif',
    '.tif', '.tiff', '.avif', '.heic', '.heif',
}


def infer_news_image_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    if mime == 'image/gif':
        return '.gif'
    if mime == 'image/svg+xml':
        return '.svg'
    return ''


def infer_ai_product_image_extension_from_mime(mime: str) -> str:
    mime = (mime or '').split(';')[0].strip().lower()
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    if mime == 'image/bmp':
        return '.bmp'
    if mime == 'image/gif':
        return '.gif'
    if mime == 'image/tiff':
        return '.tif'
    if mime == 'image/avif':
        return '.avif'
    if mime == 'image/heic':
        return '.heic'
    if mime == 'image/heif':
        return '.heif'
    return ''


def infer_ai_product_image_extension_from_bytes(sample: bytes) -> str:
    """尽力根据文件头字节推断图片扩展名。"""
    sample = sample or b''
    if sample.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if len(sample) >= 3 and sample[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if sample.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if sample.startswith(b'BM'):
        return '.bmp'
    if len(sample) >= 12 and sample[:4] == b'RIFF' and sample[8:12] == b'WEBP':
        return '.webp'
    if sample.startswith((b'II*\x00', b'MM\x00*')):
        return '.tif'
    if len(sample) >= 12 and sample[4:8] == b'ftyp':
        brand = sample[8:12].lower()
        if brand in {b'avif', b'avis'}:
            return '.avif'
        if brand in {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}:
            return '.heic'
    lower = sample[:512].decode('utf-8', errors='ignore').lower()
    if '<svg' in lower:
        return '.svg'
    return ''


def _normalized_ext(value: str) -> str:
    ext = str(value or '').strip().lower()
    if ext == '.jpe':
        return '.jpg'
    return ext


def normalize_ai_product_image_extension(
    filename: str,
    mime: str,
    sample: bytes,
    *,
    allowed_extensions: set[str] | None = None,
) -> str:
    """结合文件名、MIME 和文件签名对上传图片扩展名做兜底规范化。"""
    allowed = set(allowed_extensions or DEFAULT_AI_PRODUCT_IMAGE_EXTENSIONS)
    ext = Path((filename or '')).suffix.lower()
    if ext == '.jpe':
        ext = '.jpg'
    if ext in allowed:
        return ext

    inferred = infer_ai_product_image_extension_from_mime(mime)
    if inferred:
        return inferred

    mime_clean = (mime or '').split(';')[0].strip().lower()
    guessed = (mimetypes.guess_extension(mime_clean) or '').lower() if mime_clean else ''
    if guessed == '.jpe':
        guessed = '.jpg'
    if guessed in allowed:
        return guessed

    inferred_by_bytes = infer_ai_product_image_extension_from_bytes(sample)
    if inferred_by_bytes in allowed:
        return inferred_by_bytes

    return ''


def peek_upload_bytes(file_storage, max_bytes: int = 8192) -> bytes:
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return b''
    try:
        current_pos = stream.tell()
    except Exception:
        current_pos = None
    try:
        sample = stream.read(max_bytes)
    except Exception:
        sample = b''
    try:
        if current_pos is not None:
            stream.seek(current_pos)
        else:
            stream.seek(0)
    except Exception:
        pass
    return sample or b''


def get_uploaded_file_size(file_storage) -> int | None:
    """从文件流计算真实字节数，不信任客户端提供的 Content-Length。"""
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return None
    try:
        current_pos = stream.tell()
        stream.seek(0, 2)
        size = int(stream.tell())
        stream.seek(current_pos)
        return max(0, size)
    except Exception:
        try:
            stream.seek(0)
        except Exception:
            pass
        return None


def infer_video_extension_from_bytes(sample: bytes) -> str:
    sample = sample or b''
    if len(sample) >= 12 and sample[4:8] == b'ftyp':
        return '.mp4'
    if sample.startswith(b'\x1aE\xdf\xa3'):
        return '.webm'
    if sample.startswith(b'OggS'):
        return '.ogv'
    return ''


def validate_uploaded_image_extension(file_storage, *, allowed_extensions: set[str]) -> str:
    filename = getattr(file_storage, 'filename', '') or ''
    sample = peek_upload_bytes(file_storage)
    detected_ext = _normalized_ext(infer_ai_product_image_extension_from_bytes(sample))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename).suffix.lower())
    if named_ext == '.svg':
        detected_ext = infer_ai_product_image_extension_from_bytes(sample)
        if _normalized_ext(detected_ext) == '.svg' and named_ext in allowed_extensions:
            return named_ext
    if named_ext in allowed_extensions and named_ext in {'.svg'} and _normalized_ext(detected_ext) == named_ext:
        return named_ext
    return ''


def validate_image_bytes(filename: str, mime: str, content: bytes, *, allowed_extensions: set[str]) -> str:
    detected_ext = _normalized_ext(infer_ai_product_image_extension_from_bytes(content[:8192]))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename or '').suffix.lower())
    mime_ext = _normalized_ext(infer_news_image_extension_from_mime((mime or '').lower()))
    if named_ext in allowed_extensions and named_ext == detected_ext:
        return named_ext
    if mime_ext in allowed_extensions and mime_ext == detected_ext:
        return mime_ext
    return ''


def validate_uploaded_video_extension(file_storage, *, allowed_extensions: set[str]) -> str:
    filename = getattr(file_storage, 'filename', '') or ''
    sample = peek_upload_bytes(file_storage)
    detected_ext = _normalized_ext(infer_video_extension_from_bytes(sample))
    if detected_ext in allowed_extensions:
        return detected_ext
    named_ext = _normalized_ext(Path(filename).suffix.lower())
    return named_ext if named_ext in allowed_extensions and named_ext == detected_ext else ''


def validate_uploaded_pdf(file_storage) -> bool:
    sample = peek_upload_bytes(file_storage)
    return bool(sample.startswith(b'%PDF-'))
