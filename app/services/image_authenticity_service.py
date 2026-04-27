from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session

from app.core.config import settings
from app.models.file_info import FileInfo
from app.models.user import User
from app.services.errors import ServiceError
from app.services.file_service import get_file_for_user

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_PDF_TYPE = "application/pdf"

MAGIC_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
    "application/pdf": (b"%PDF",),
}


def check_image_authenticity(
    db: Session,
    user: User,
    *,
    file_id: str,
    run_c2pa: bool = True,
    run_external: bool = True,
) -> dict:
    record = get_file_for_user(db, user, file_id)
    path = Path(record.storage_path)
    file_kind = _detect_file_kind(record)
    if file_kind == "unsupported":
        raise ServiceError("仅支持图片或 PDF 证明文件", 1008)
    if not path.exists() or not path.is_file():
        raise ServiceError("file not found", 1002)

    metadata_check = _run_metadata_check(record, path)
    c2pa_check = _run_c2pa_check(path) if run_c2pa else _skipped_check("provenance", "C2PA / Content Credentials 溯源校验")
    external_check = (
        _run_external_detector(record, path, file_kind)
        if run_external
        else _skipped_check("external_ensemble", "外部高精度鉴别服务")
    )
    checks = [metadata_check, c2pa_check, external_check]
    fusion = _fuse_checks(checks)

    return {
        "file_id": record.id,
        "filename": record.original_name,
        "content_type": record.content_type,
        "file_kind": file_kind,
        "enabled": True,
        "status": "completed",
        "provider": settings.image_authenticity_provider,
        "model": settings.image_authenticity_model,
        "result": fusion["result"],
        "risk_level": fusion["risk_level"],
        "confidence": fusion["confidence"],
        "message": fusion["message"],
        "summary": fusion["summary"],
        "checks": checks,
        "pipeline": _recommended_pipeline(),
        "integration": {
            "endpoint": settings.image_authenticity_api_url,
            "api_key_configured": bool(settings.image_authenticity_api_key),
            "timeout_seconds": settings.image_authenticity_timeout_seconds,
            "c2patool_path": settings.image_authenticity_c2patool_path,
            "business_flow_enabled": False,
        },
        "limitations": [
            "未命中 C2PA 或水印不等于文件一定造假，很多真实图片会被平台或截图流程移除来源凭证。",
            "AI 生成图和 P 图检测属于概率判断，奖状截图、PDF 拼接、二次压缩会显著影响单模型准确率。",
            "本接口当前独立调用，不参与申报、审核、归档、计分等业务流转。",
        ],
    }


def _run_metadata_check(record: FileInfo, path: Path) -> dict:
    detected_type = _detect_magic_content_type(path)
    expected_type = (record.content_type or "").lower() or None
    extension_type = _extension_content_type(path.name)
    warnings = []
    matched = True

    if expected_type and detected_type and expected_type != detected_type:
        matched = False
        warnings.append(f"数据库 content_type={expected_type}，文件头识别={detected_type}")
    if extension_type and detected_type and extension_type != detected_type:
        matched = False
        warnings.append(f"文件扩展名类型={extension_type}，文件头识别={detected_type}")
    if path.stat().st_size != record.size:
        warnings.append(f"数据库大小={record.size}，实际文件大小={path.stat().st_size}")

    status = "passed" if matched else "warning"
    return {
        "key": "metadata",
        "name": "文件格式 / 元数据一致性检查",
        "status": status,
        "result": "consistent" if matched else "inconsistent",
        "confidence": 0.55 if matched else 0.75,
        "signals": {
            "stored_content_type": expected_type,
            "extension_content_type": extension_type,
            "magic_content_type": detected_type,
            "stored_size": record.size,
            "actual_size": path.stat().st_size,
            "md5": record.md5,
        },
        "warnings": warnings,
    }


def _run_c2pa_check(path: Path) -> dict:
    tool = shutil.which(settings.image_authenticity_c2patool_path)
    if not tool:
        return {
            "key": "provenance",
            "name": "C2PA / Content Credentials 溯源校验",
            "status": "unavailable",
            "result": "not_checked",
            "confidence": 0.0,
            "message": "未找到 c2patool，可安装后通过 IMAGE_AUTHENTICITY_C2PATOOL_PATH 指定。",
        }

    command = [tool, str(path), "--json"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1.0, settings.image_authenticity_timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "key": "provenance",
            "name": "C2PA / Content Credentials 溯源校验",
            "status": "failed",
            "result": "timeout",
            "confidence": 0.0,
            "message": "c2patool 执行超时。",
        }

    payload = _safe_json_loads(completed.stdout)
    stderr = (completed.stderr or "").strip()
    manifest_count = _count_c2pa_manifests(payload)
    if completed.returncode == 0 and manifest_count > 0:
        return {
            "key": "provenance",
            "name": "C2PA / Content Credentials 溯源校验",
            "status": "passed",
            "result": "content_credentials_found",
            "confidence": 0.95,
            "signals": {
                "manifest_count": manifest_count,
                "tool_return_code": completed.returncode,
            },
            "raw": _trim_payload(payload),
        }
    return {
        "key": "provenance",
        "name": "C2PA / Content Credentials 溯源校验",
        "status": "warning" if completed.returncode != 0 else "completed",
        "result": "content_credentials_not_found",
        "confidence": 0.25,
        "message": stderr or "未检测到可验证的 C2PA 内容凭证。",
        "signals": {
            "manifest_count": manifest_count,
            "tool_return_code": completed.returncode,
        },
    }


def _run_external_detector(record: FileInfo, path: Path, file_kind: str) -> dict:
    if not settings.image_authenticity_api_url:
        return {
            "key": "external_ensemble",
            "name": "外部高精度鉴别服务",
            "status": "not_configured",
            "result": "not_checked",
            "confidence": 0.0,
            "message": "未配置 IMAGE_AUTHENTICITY_API_URL，当前只执行本地轻量检查。",
            "expected_response": {
                "ai_generated_probability": "0.0-1.0",
                "tampering_probability": "0.0-1.0",
                "watermark": {"detected": False, "provider": "synthid|c2pa|other"},
                "tampering_regions": [{"page": 1, "bbox": [0, 0, 100, 100], "score": 0.9}],
                "page_results": [{"page": 1, "risk_level": "low", "score": 0.12}],
                "model_versions": {"trufor": "checkpoint-name", "ai_detector": "checkpoint-name"},
            },
        }

    headers = {}
    if settings.image_authenticity_api_key:
        headers["Authorization"] = f"Bearer {settings.image_authenticity_api_key}"
    data = {
        "file_id": record.id,
        "filename": record.original_name,
        "file_kind": file_kind,
        "model": settings.image_authenticity_model,
        "pipeline": "c2pa,synthid,trufor,universal_fake_detect",
    }
    try:
        with path.open("rb") as handle:
            files = {"file": (record.original_name, handle, record.content_type or "application/octet-stream")}
            response = httpx.post(
                settings.image_authenticity_api_url,
                headers=headers,
                data=data,
                files=files,
                timeout=settings.image_authenticity_timeout_seconds,
            )
        response.raise_for_status()
    except Exception as exc:
        return {
            "key": "external_ensemble",
            "name": "外部高精度鉴别服务",
            "status": "failed",
            "result": "error",
            "confidence": 0.0,
            "message": str(exc),
        }

    payload = _safe_json_loads(response.text)
    ai_probability = _coerce_probability(payload.get("ai_generated_probability"))
    tampering_probability = _coerce_probability(payload.get("tampering_probability"))
    status = "passed"
    result = "likely_real"
    if ai_probability >= 0.8 and tampering_probability >= 0.8:
        result = "suspected_ai_generated_and_tampered"
        status = "warning"
    elif ai_probability >= 0.8:
        result = "suspected_ai_generated"
        status = "warning"
    elif tampering_probability >= 0.8:
        result = "suspected_tampered"
        status = "warning"

    return {
        "key": "external_ensemble",
        "name": "外部高精度鉴别服务",
        "status": status,
        "result": result,
        "confidence": max(ai_probability, tampering_probability),
        "signals": {
            "ai_generated_probability": ai_probability,
            "tampering_probability": tampering_probability,
            "watermark": payload.get("watermark"),
            "tampering_regions": payload.get("tampering_regions") or [],
            "page_results": payload.get("page_results") or [],
            "model_versions": payload.get("model_versions") or {},
            "provider_result": payload.get("result"),
        },
        "raw": _trim_payload(payload),
    }


def _fuse_checks(checks: list[dict]) -> dict:
    metadata = _find_check(checks, "metadata")
    c2pa = _find_check(checks, "provenance")
    external = _find_check(checks, "external_ensemble")
    summary = []

    if metadata and metadata.get("status") == "warning":
        summary.append("文件格式或元数据存在不一致，需要人工确认。")
    if c2pa and c2pa.get("result") == "content_credentials_found":
        summary.append("检测到 C2PA 内容凭证，可作为强溯源信号。")
    elif c2pa and c2pa.get("status") in {"completed", "warning"}:
        summary.append("未检测到 C2PA 内容凭证；这不是造假证据，只表示缺少可验证来源。")
    if external and external.get("status") == "not_configured":
        summary.append("外部 AI 生成图/P 图检测服务未配置，未执行概率模型。")

    if external and external.get("result") == "suspected_ai_generated_and_tampered":
        return _fusion("suspected_ai_generated_and_tampered", "high", external.get("confidence", 0.8), "疑似 AI 生成且存在篡改风险。", summary)
    if external and external.get("result") == "suspected_ai_generated":
        return _fusion("suspected_ai_generated", "high", external.get("confidence", 0.8), "疑似 AI 生成图片。", summary)
    if external and external.get("result") == "suspected_tampered":
        return _fusion("suspected_tampered", "high", external.get("confidence", 0.8), "疑似存在 P 图或局部篡改。", summary)
    if metadata and metadata.get("status") == "warning":
        return _fusion("needs_manual_review", "medium", metadata.get("confidence", 0.6), "本地检查发现异常，建议人工复核。", summary)
    if c2pa and c2pa.get("result") == "content_credentials_found" and external and external.get("result") == "likely_real":
        return _fusion("likely_authentic", "low", 0.85, "溯源凭证存在，外部检测未发现明显风险。", summary)
    if external and external.get("result") == "likely_real":
        return _fusion("likely_real", "low", external.get("confidence", 0.5), "外部检测未发现明显 AI 生成或篡改风险。", summary)

    return _fusion("inconclusive", "unknown", 0.0, "当前证据不足，不能判断是否 AI 生成或 P 图。", summary)


def _recommended_pipeline() -> list[dict]:
    return [
        {
            "key": "provenance",
            "name": "C2PA / Content Credentials",
            "purpose": "优先读取可验证来源、编辑历史和签名。",
            "recommended_tool": "contentauth/c2patool 或 c2pa-python",
            "weight": "强证据",
        },
        {
            "key": "watermark",
            "name": "SynthID / 供应商水印",
            "purpose": "检测 Google AI 等已嵌入水印的生成内容。",
            "recommended_tool": "SynthID Detector 或供应商 API",
            "weight": "强证据，但覆盖有限",
        },
        {
            "key": "tampering_localization",
            "name": "P 图 / 篡改定位",
            "purpose": "输出整图完整性分、局部热力图和可疑区域。",
            "recommended_tool": "TruFor，必要时叠加 MVSS-Net/CAT-Net 类模型",
            "weight": "概率证据",
        },
        {
            "key": "ai_generated",
            "name": "AI 生成图检测",
            "purpose": "识别扩散模型、GAN 和新生成器产生的图片。",
            "recommended_tool": "UniversalFakeDetect + AI-GenBench 持续评测/校准",
            "weight": "概率证据",
        },
        {
            "key": "fusion",
            "name": "证据融合",
            "purpose": "对来源、水印、篡改定位、AI 生成概率做阈值融合，只输出风险提示。",
            "recommended_tool": "校内奖状样本集上重新校准阈值",
            "weight": "最终接口结论",
        },
    ]


def _detect_file_kind(record: FileInfo) -> str:
    content_type = (record.content_type or "").lower()
    suffix = Path(record.original_name or record.id).suffix.lower()
    if content_type in SUPPORTED_IMAGE_TYPES or suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    if content_type == SUPPORTED_PDF_TYPE or suffix == ".pdf":
        return "pdf"
    return "unsupported"


def _detect_magic_content_type(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return None
    if head.startswith(MAGIC_SIGNATURES["image/jpeg"]):
        return "image/jpeg"
    if head.startswith(MAGIC_SIGNATURES["image/png"]):
        return "image/png"
    if head.startswith(MAGIC_SIGNATURES["application/pdf"]):
        return "application/pdf"
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _extension_content_type(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".pdf":
        return "application/pdf"
    return None


def _skipped_check(key: str, name: str) -> dict:
    return {
        "key": key,
        "name": name,
        "status": "skipped",
        "result": "not_checked",
        "confidence": 0.0,
    }


def _safe_json_loads(value: str | bytes | None) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {"raw": str(value)[:2000]}
    return payload if isinstance(payload, dict) else {"value": payload}


def _count_c2pa_manifests(payload: dict) -> int:
    if not payload:
        return 0
    if isinstance(payload.get("manifests"), dict):
        return len(payload["manifests"])
    if isinstance(payload.get("active_manifest"), dict):
        return 1
    if isinstance(payload.get("manifest_store"), dict):
        manifests = payload["manifest_store"].get("manifests")
        if isinstance(manifests, dict):
            return len(manifests)
    return 0


def _coerce_probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))


def _find_check(checks: list[dict], key: str) -> dict | None:
    return next((item for item in checks if item.get("key") == key), None)


def _fusion(result: str, risk_level: str, confidence: float, message: str, summary: list[str]) -> dict:
    return {
        "result": result,
        "risk_level": risk_level,
        "confidence": round(float(confidence or 0.0), 4),
        "message": message,
        "summary": summary,
    }


def _trim_payload(payload: dict) -> dict:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= 4000:
        return payload
    return {"truncated": True, "preview": text[:4000]}
