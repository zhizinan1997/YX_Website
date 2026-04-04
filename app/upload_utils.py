"""共享的上传与媒体校验辅助模块。"""

from __future__ import annotations

import mimetypes
from pathlib import Path

DEFAULT_AI_PRODUCT_IMAGE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif',
    '.tif', '.tiff', '.avif', '.heic', '.heif',
}


def infer_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'video/mp4':
        return '.mp4'
    return ''


def infer_partner_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    return ''


def infer_h2_home_video_extension_from_mime(mime: str) -> str:
    if mime == 'video/mp4':
        return '.mp4'
    if mime == 'video/webm':
        return '.webm'
    if mime == 'video/ogg':
        return '.ogv'
    return ''


def infer_product_card_extension_from_mime(mime: str) -> str:
    if mime == 'image/png':
        return '.png'
    if mime == 'image/jpeg':
        return '.jpg'
    if mime == 'image/webp':
        return '.webp'
    return ''


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
