import hashlib
import hmac
import os
import time
import uuid

from ..config import settings

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
DOC_MIMES = {"application/pdf", "application/msword",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "text/plain"}
AUDIO_MIMES = {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/webm", "audio/wav"}
ALLOWED = IMAGE_MIMES | DOC_MIMES


def upload_dir() -> str:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    return settings.UPLOAD_DIR


def store(data: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    day = time.strftime("%Y/%m")
    rel = f"{day}/{uuid.uuid4().hex}{ext}"
    path = os.path.join(upload_dir(), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return rel


def abs_path(storage_key: str) -> str:
    return os.path.join(upload_dir(), storage_key)


def _sig(att_id: int, exp: int) -> str:
    return hmac.new(settings.FILE_SIGNING_SECRET.encode(), f"{att_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(att_id: int, ttl: int = 300) -> str:
    exp = int(time.time()) + ttl
    return f"{settings.PUBLIC_API_URL}/files/{att_id}?exp={exp}&sig={_sig(att_id, exp)}"


def verify_sig(att_id: int, exp: int, sig: str) -> bool:
    return exp > time.time() and hmac.compare_digest(_sig(att_id, exp), sig)
