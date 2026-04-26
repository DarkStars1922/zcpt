from pathlib import Path

from sqlmodel import Session

from app.core.config import settings
from app.models.file_info import FileInfo
from app.models.user import User
from app.services.errors import ServiceError
from app.services.file_service import get_file_for_user

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_PDF_TYPE = "application/pdf"


def plan_image_authenticity_check(db: Session, user: User, *, file_id: str) -> dict:
    record = get_file_for_user(db, user, file_id)
    file_kind = _detect_file_kind(record)
    if file_kind == "unsupported":
        raise ServiceError("仅支持图片或 PDF 证明文件", 1008)

    return {
        "file_id": record.id,
        "filename": record.original_name,
        "content_type": record.content_type,
        "file_kind": file_kind,
        "enabled": False,
        "status": "reserved",
        "provider": settings.image_authenticity_provider,
        "result": "not_evaluated",
        "message": "图片真实性检测接口已预留，当前未启用实际判定模型。",
        "checks": [
            {
                "key": "provenance",
                "name": "C2PA / Content Credentials 溯源校验",
                "status": "planned",
                "description": "读取并验证内容凭证、签名、来源设备、编辑动作和内容绑定。",
            },
            {
                "key": "metadata",
                "name": "EXIF / 文件元数据异常检查",
                "status": "planned",
                "description": "检查拍摄设备、时间、软件、编码链路和重复压缩等辅助线索。",
            },
            {
                "key": "watermark",
                "name": "AI 水印检测",
                "status": "planned",
                "description": "预留 SynthID 等水印服务或供应商 SDK 的接入位置。",
            },
            {
                "key": "tampering_localization",
                "name": "P 图 / 篡改定位",
                "status": "planned",
                "description": "预留局部篡改检测模型，后续可输出热力图、置信度和风险区域。",
            },
            {
                "key": "ai_generated",
                "name": "AI 生成图片检测",
                "status": "planned",
                "description": "预留通用生成图检测模型，只作为辅助线索，不单独作为最终结论。",
            },
        ],
        "integration": {
            "endpoint": settings.image_authenticity_api_url,
            "api_key_configured": bool(settings.image_authenticity_api_key),
            "model": settings.image_authenticity_model,
        },
        "roadmap": [
            "先做 C2PA / Content Credentials 可验证溯源，低误报且解释性强。",
            "再接入图像篡改定位模型输出风险区域，用于辅助人工复核。",
            "最后叠加 AI 生成图片检测和水印检测，结果只作为风险提示。",
        ],
    }


def _detect_file_kind(record: FileInfo) -> str:
    content_type = (record.content_type or "").lower()
    suffix = Path(record.original_name or record.id).suffix.lower()
    if content_type in SUPPORTED_IMAGE_TYPES or suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    if content_type == SUPPORTED_PDF_TYPE or suffix == ".pdf":
        return "pdf"
    return "unsupported"

