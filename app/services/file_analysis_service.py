from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.core.utils import json_dumps, json_loads, utcnow
from app.models.file_analysis_result import FileAnalysisResult
from app.models.file_info import FileInfo
from app.models.user import User
from app.services.ocr import OCRServiceUnavailableError, extract_seal_and_signature, run_document_ocr

LEVEL_KEYWORDS = (
    "国际级",
    "国家级",
    "省级",
    "市级",
    "校级",
    "院级",
    "院系级",
    "班级",
    "特等奖",
    "一等奖",
    "二等奖",
    "三等奖",
    "金奖",
    "银奖",
    "铜奖",
    "优秀奖",
)
TITLE_HINTS = ("证书", "证明", "获奖", "奖", "竞赛", "荣誉", "表彰", "志愿", "创新", "一等奖", "二等奖", "三等奖")


def analyze_file(db: Session, file: FileInfo, *, uploader: User | None = None, force: bool = False) -> FileAnalysisResult:
    record = db.exec(select(FileAnalysisResult).where(FileAnalysisResult.file_id == file.id)).first()
    if not record:
        record = FileAnalysisResult(file_id=file.id, provider=settings.ai_audit_provider)
        db.add(record)
        db.commit()
        db.refresh(record)

    if record.status == "completed" and not force:
        return record

    record.provider = settings.ai_audit_provider
    record.status = "running"
    record.error_message = None
    record.updated_at = utcnow()
    db.add(record)
    db.commit()

    try:
        raw_result = run_document_ocr(Path(file.storage_path))
        summary = _build_summary(file=file, uploader=uploader, raw_result=raw_result)
        record.status = "completed"
        record.ocr_text = raw_result["ocr_text"] or None
        record.analysis_json = json_dumps(summary)
        record.error_message = None
        record.updated_at = utcnow()
        record.analyzed_at = utcnow()
    except OCRServiceUnavailableError as exc:
        record.status = "failed"
        record.ocr_text = None
        record.analysis_json = json_dumps({"reason": str(exc)})
        record.error_message = str(exc)
        record.updated_at = utcnow()
    except Exception as exc:
        record.status = "failed"
        record.ocr_text = None
        record.analysis_json = json_dumps({"reason": str(exc)})
        record.error_message = str(exc)
        record.updated_at = utcnow()

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_file_analysis_record(db: Session, file_id: str) -> FileAnalysisResult | None:
    return db.exec(select(FileAnalysisResult).where(FileAnalysisResult.file_id == file_id)).first()


def get_file_analysis_payload(record: FileAnalysisResult | None) -> dict:
    if not record:
        return {}
    payload = json_loads(record.analysis_json, {})
    if not isinstance(payload, dict):
        return {}
    return payload


def _build_summary(*, file: FileInfo, uploader: User | None, raw_result: dict) -> dict:
    pages = raw_result.get("ocr_pages") or []
    full_text = raw_result.get("ocr_text") or ""
    document_title = _extract_document_title(pages, file.original_name)
    seal_and_signature = extract_seal_and_signature(
        ocr_pages=pages,
        layout_pages=raw_result.get("layout_pages") or [],
        uploader_name=uploader.name if uploader else None,
        seal_score_threshold=settings.paddleocr_seal_score_threshold,
    )
    return {
        "document_title": document_title,
        "recognized_levels": _extract_levels(full_text, document_title, file.original_name),
        "uploader_name_match": _match_name(
            full_text,
            [
                uploader.name if uploader else None,
                uploader.account if uploader else None,
            ],
            pages=pages,
        ),
        "filename_vs_document_title": _compare_filename(file.original_name, document_title),
        "seal": seal_and_signature["seal"],
        "signature": seal_and_signature["signature"],
        "page_count": len(pages),
        "pages": pages,
    }


def _extract_document_title(pages: list[dict], original_name: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    if pages:
        first_page_lines = pages[0].get("lines", [])
        for index, line in enumerate(first_page_lines[:6]):
            text = (line.get("text") or "").strip()
            if len(text) < 4:
                continue
            score = min(len(text), 30)
            if any(hint in text for hint in TITLE_HINTS):
                score += 40
            if any(char.isdigit() for char in text):
                score -= 18
            score -= index * 5
            candidates.append((score, index, text))
    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][2]
    return Path(original_name).stem


def _extract_levels(*texts: str) -> list[str]:
    matched = []
    haystack = "\n".join(filter(None, texts))
    for keyword in LEVEL_KEYWORDS:
        if keyword in haystack and keyword not in matched:
            matched.append(keyword)
    return matched


def _match_name(text: str, expected_names: list[str | None], *, pages: list[dict] | None = None) -> dict:
    candidates = [name.strip() for name in expected_names if isinstance(name, str) and name.strip()]
    recognized_candidates = _extract_name_candidates(text)
    if not candidates:
        return {
            "expected_name": None,
            "expected_candidates": [],
            "matched": None,
            "matches": [],
            "matched_page_indexes": [],
            "recognized_name_candidates": recognized_candidates,
        }
    normalized_text = _normalize_text(text)
    matches = [name for name in candidates if _normalize_text(name) and _normalize_text(name) in normalized_text]
    matched = bool(matches)
    matched_page_indexes = _find_matching_page_indexes(pages or [], candidates)
    for name in matches:
        if name not in recognized_candidates:
            recognized_candidates.insert(0, name)
    return {
        "expected_name": candidates[0],
        "expected_candidates": candidates,
        "matched": matched,
        "matches": matches,
        "matched_page_indexes": matched_page_indexes,
        "recognized_name_candidates": recognized_candidates,
    }


def _extract_name_candidates(text: str) -> list[str]:
    if not text:
        return []
    patterns = [
        "(?:姓名|获奖者|获奖学生|学生姓名|参赛者|参赛学生|作者|申报人|申请人)[:：\\s]*([\\u4e00-\\u9fff]{2,4})",
        "([\\u4e00-\\u9fff]{2,4})同学",
        "授予[:：\\s]*([\\u4e00-\\u9fff]{2,4})",
        "(?:Name|Student|Applicant)[:：\\s]*([A-Za-z][A-Za-z ._-]{1,40})",
    ]
    ignored = {"学生", "姓名", "获奖", "证书", "大学", "学院", "学校", "项目", "成员"}
    results: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" ：:，,。.;；")
            if not value or value in ignored or value in results:
                continue
            results.append(value)
            if len(results) >= 8:
                return results
    return results


def _find_matching_page_indexes(pages: list[dict], candidates: list[str]) -> list[int]:
    result = []
    normalized_candidates = [_normalize_text(candidate) for candidate in candidates if _normalize_text(candidate)]
    if not normalized_candidates:
        return result
    for fallback_index, page in enumerate(pages):
        page_text = page.get("text") or "\n".join(line.get("text") or "" for line in page.get("lines", []))
        normalized_page_text = _normalize_text(page_text)
        if any(candidate in normalized_page_text for candidate in normalized_candidates):
            page_index = page.get("page_index", fallback_index)
            try:
                result.append(int(page_index))
            except (TypeError, ValueError):
                result.append(fallback_index)
    return result


def _compare_filename(filename: str, document_title: str | None) -> dict:
    source_name = Path(filename).stem
    similarity = _text_similarity(source_name, document_title or "")
    return {
        "filename": filename,
        "document_title": document_title,
        "matched": similarity >= 0.68,
        "similarity": similarity,
    }


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 1.0
    return round(SequenceMatcher(None, normalized_left, normalized_right).ratio(), 4)


def _normalize_text(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
