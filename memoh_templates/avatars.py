"""Read reviewed avatar thumbnails without network access."""
import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def image_bytes(record):
    path = record.get('path', '')
    if not re.fullmatch(r'assets/avatars/[a-z0-9-]+\.jpg', path):
        raise ValueError('头像路径必须位于 assets/avatars/')
    raw = (ROOT / path).read_bytes()
    if not raw.startswith(b'\xff\xd8') or not raw.endswith(b'\xff\xd9'):
        raise ValueError('头像不是有效的 JPEG：' + path)
    if record.get('sha256') and hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise ValueError('头像校验不一致：' + path)
    return raw


def data_url(record):
    return 'data:image/jpeg;base64,' + base64.b64encode(image_bytes(record)).decode('ascii')
