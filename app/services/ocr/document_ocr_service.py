from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings


class OCRServiceUnavailableError(RuntimeError):
    pass


def run_document_ocr(file_path: Path) -> dict:
    if not settings.file_analysis_enabled:
        raise OCRServiceUnavailableError("file analysis is disabled")
    if not file_path.exists() or not file_path.is_file():
        raise OCRServiceUnavailableError("file not found")

    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", settings.paddle_model_source)
    ocr_pages = _predict_general_ocr(file_path)
    try:
        layout_pages = _predict_layout(file_path)
    except OCRServiceUnavailableError:
        layout_pages = []
    return {
        "ocr_pages": ocr_pages,
        "layout_pages": layout_pages,
        "ocr_text": "\n".join(page["text"] for page in ocr_pages if page["text"]).strip(),
    }


@lru_cache(maxsize=1)
def _get_ocr_model():
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to import PaddleOCR: {exc}") from exc

    try:
        det_model_dir = _resolve_model_dir(
            settings.paddleocr_text_detection_model_dir,
            settings.paddleocr_text_detection_model_name,
        )
        rec_model_dir = _resolve_model_dir(
            settings.paddleocr_text_recognition_model_dir,
            settings.paddleocr_text_recognition_model_name,
        )
        return PaddleOCR(
            text_detection_model_name=settings.paddleocr_text_detection_model_name,
            text_detection_model_dir=str(det_model_dir),
            text_recognition_model_name=settings.paddleocr_text_recognition_model_name,
            text_recognition_model_dir=str(rec_model_dir),
            use_doc_orientation_classify=settings.paddleocr_use_doc_orientation_classify,
            use_doc_unwarping=False,
            use_textline_orientation=settings.paddleocr_use_textline_orientation,
            device=settings.paddleocr_device,
            enable_mkldnn=settings.paddleocr_enable_mkldnn,
            cpu_threads=settings.paddleocr_cpu_threads,
        )
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to initialize PaddleOCR pipeline: {exc}") from exc


@lru_cache(maxsize=1)
def _get_layout_model():
    try:
        from paddleocr import LayoutDetection
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to import LayoutDetection: {exc}") from exc

    try:
        layout_model_dir = _resolve_model_dir(
            settings.paddleocr_layout_detection_model_dir,
            settings.paddleocr_layout_detection_model_name,
        )
        return LayoutDetection(
            model_name=settings.paddleocr_layout_detection_model_name,
            model_dir=str(layout_model_dir),
            device=settings.paddleocr_device,
            enable_mkldnn=settings.paddleocr_enable_mkldnn,
            cpu_threads=settings.paddleocr_cpu_threads,
        )
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to initialize layout detector: {exc}") from exc


def _predict_general_ocr(file_path: Path) -> list[dict]:
    model = _get_ocr_model()
    pages = []
    try:
        for index, res in enumerate(model.predict(str(file_path))):
            payload = _extract_payload(res)
            lines = []
            texts = payload.get("rec_texts") or []
            scores = payload.get("rec_scores") or []
            boxes = payload.get("rec_boxes") or payload.get("rec_polys") or []
            for line_index, text in enumerate(texts):
                normalized_text = str(text).strip()
                if not normalized_text:
                    continue
                score = _safe_float(scores[line_index] if line_index < len(scores) else None)
                box = _to_plain(boxes[line_index]) if line_index < len(boxes) else None
                lines.append({"text": normalized_text, "score": score, "box": box})
            pages.append(
                {
                    "page_index": payload.get("page_index", index),
                    "text": "\n".join(item["text"] for item in lines).strip(),
                    "lines": lines,
                    "width": _infer_page_size(lines, axis=0),
                    "height": _infer_page_size(lines, axis=1),
                }
            )
    except OCRServiceUnavailableError:
        raise
    except Exception as exc:
        raise OCRServiceUnavailableError(f"general OCR inference failed: {exc}") from exc
    return pages


def _predict_layout(file_path: Path) -> list[dict]:
    model = _get_layout_model()
    pages = []
    try:
        for index, res in enumerate(model.predict(str(file_path), batch_size=1, layout_nms=True)):
            payload = _extract_payload(res)
            boxes = []
            for item in payload.get("boxes") or []:
                boxes.append(
                    {
                        "label": item.get("label"),
                        "score": _safe_float(item.get("score")),
                        "coordinate": _to_plain(item.get("coordinate")),
                    }
                )
            pages.append({"page_index": payload.get("page_index", index), "boxes": boxes})
    except OCRServiceUnavailableError:
        raise
    except Exception as exc:
        raise OCRServiceUnavailableError(f"layout detection failed: {exc}") from exc
    return pages


def _extract_payload(result: Any) -> dict:
    data: Any = result
    if hasattr(result, "json"):
        data = result.json
    if callable(data):
        data = data()
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return data["res"]
    if isinstance(data, dict):
        return data
    raise OCRServiceUnavailableError(f"unsupported PaddleOCR result payload: {type(result)!r}")


def _to_plain(value: Any):
    if value is None:
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_page_size(lines: list[dict], *, axis: int) -> float | None:
    points = []
    for line in lines:
        box = line.get("box")
        if not box:
            continue
        if isinstance(box, list) and len(box) == 4 and all(isinstance(item, (int, float)) for item in box):
            points.append(float(box[axis + 2]))
            continue
        if isinstance(box, list):
            for point in box:
                if isinstance(point, list) and len(point) >= 2:
                    points.append(float(point[axis]))
    if not points:
        return None
    return max(points)


def _resolve_model_dir(override_dir: str | None, model_name: str) -> Path:
    base_dir = Path(override_dir) if override_dir else settings.paddle_model_dir_path / model_name
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir
