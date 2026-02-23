from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}
CONTENT_TYPE_EXT_MAP = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


class FileError(Exception):
    def __init__(self, message: str, code: int = 1008):
        self.message = message
        self.code = code
        super().__init__(message)


def _get_upload_dir() -> Path:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _detect_extension(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    ext = CONTENT_TYPE_EXT_MAP.get(content_type)
    if ext:
        return ext

    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    raise FileError("文件类型不支持，仅支持 jpg/png/webp/pdf")


def _validate_content_type(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    if content_type and content_type in ALLOWED_CONTENT_TYPES:
        return

    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        return

    raise FileError("文件类型不支持，仅支持 jpg/png/webp/pdf")


async def save_upload_file(file: UploadFile) -> dict:
    _validate_content_type(file)

    max_file_size = settings.upload_max_file_size or DEFAULT_MAX_FILE_SIZE
    ext = _detect_extension(file)
    file_id = f"{uuid4().hex}{ext}"
    save_dir = _get_upload_dir()
    file_path = save_dir / file_id

    size = 0
    with file_path.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_file_size:
                output.close()
                file_path.unlink(missing_ok=True)
                raise FileError("文件大小超限")
            output.write(chunk)

    return {
        "file_id": file_id,
        "filename": file.filename or file_id,
        "content_type": (file.content_type or "").lower() or None,
        "size": size,
    }


def get_file_path(file_id: str) -> Path:
    if not file_id or "/" in file_id or ".." in file_id:
        raise FileError("文件不存在", code=1002)

    file_path = _get_upload_dir() / file_id
    if not file_path.exists() or not file_path.is_file():
        raise FileError("文件不存在", code=1002)

    return file_path
