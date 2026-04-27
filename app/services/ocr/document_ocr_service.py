from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings


class OCRServiceUnavailableError(RuntimeError):
    pass


PDF_RENDER_SCALE = 3.0


def run_document_ocr(file_path: Path) -> dict:
    if not settings.file_analysis_enabled:
        raise OCRServiceUnavailableError("file analysis is disabled")
    if not file_path.exists() or not file_path.is_file():
        raise OCRServiceUnavailableError("file not found")

    _configure_paddlex_env()
    page_inputs = _build_page_inputs(file_path)
    ocr_pages = _predict_general_ocr(page_inputs)
    try:
        layout_pages = _predict_layout(page_inputs)
    except OCRServiceUnavailableError:
        layout_pages = []
    return {
        "ocr_pages": ocr_pages,
        "layout_pages": layout_pages,
        "ocr_text": "\n".join(page["text"] for page in ocr_pages if page["text"]).strip(),
    }


@lru_cache(maxsize=1)
def _get_ocr_model():
    _configure_paddlex_env()
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to import PaddleOCR: {exc}") from exc

    try:
        model_kwargs = dict(
            text_detection_model_name=settings.paddleocr_text_detection_model_name,
            text_recognition_model_name=settings.paddleocr_text_recognition_model_name,
            use_doc_orientation_classify=settings.paddleocr_use_doc_orientation_classify,
            use_doc_unwarping=False,
            use_textline_orientation=settings.paddleocr_use_textline_orientation,
            device=settings.paddleocr_device,
            enable_mkldnn=settings.paddleocr_enable_mkldnn,
            cpu_threads=settings.paddleocr_cpu_threads,
        )
        det_model_dir = _resolve_model_dir(settings.paddleocr_text_detection_model_dir, "text detection")
        rec_model_dir = _resolve_model_dir(settings.paddleocr_text_recognition_model_dir, "text recognition")
        if det_model_dir:
            model_kwargs["text_detection_model_dir"] = str(det_model_dir)
        if rec_model_dir:
            model_kwargs["text_recognition_model_dir"] = str(rec_model_dir)
        return PaddleOCR(**model_kwargs)
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to initialize PaddleOCR pipeline: {exc}") from exc


@lru_cache(maxsize=1)
def _get_layout_model():
    _configure_paddlex_env()
    try:
        from paddleocr import LayoutDetection
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to import LayoutDetection: {exc}") from exc

    try:
        model_kwargs = dict(
            model_name=settings.paddleocr_layout_detection_model_name,
            device=settings.paddleocr_device,
            enable_mkldnn=settings.paddleocr_enable_mkldnn,
            cpu_threads=settings.paddleocr_cpu_threads,
        )
        layout_model_dir = _resolve_model_dir(settings.paddleocr_layout_detection_model_dir, "layout detection")
        if layout_model_dir:
            model_kwargs["model_dir"] = str(layout_model_dir)
        return LayoutDetection(**model_kwargs)
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to initialize layout detector: {exc}") from exc


def _predict_general_ocr(page_inputs: list[dict]) -> list[dict]:
    model = _get_ocr_model()
    pages = []
    try:
        for fallback_index, page_input in enumerate(page_inputs):
            for res in model.predict(page_input["input"]):
                payload = _extract_payload(res)
                lines = _extract_ocr_lines(payload)
                pages.append(
                    {
                        "page_index": payload.get("page_index", page_input.get("page_index", fallback_index)),
                        "text": "\n".join(item["text"] for item in lines).strip(),
                        "lines": lines,
                        "width": _infer_page_size(lines, axis=0) or page_input.get("width"),
                        "height": _infer_page_size(lines, axis=1) or page_input.get("height"),
                    }
                )
    except OCRServiceUnavailableError:
        raise
    except Exception as exc:
        raise OCRServiceUnavailableError(f"general OCR inference failed: {exc}") from exc
    return pages


def _predict_layout(page_inputs: list[dict]) -> list[dict]:
    model = _get_layout_model()
    pages = []
    try:
        for fallback_index, page_input in enumerate(page_inputs):
            for res in model.predict(page_input["input"], batch_size=1, layout_nms=True):
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
                pages.append({"page_index": payload.get("page_index", page_input.get("page_index", fallback_index)), "boxes": boxes})
    except OCRServiceUnavailableError:
        raise
    except Exception as exc:
        raise OCRServiceUnavailableError(f"layout detection failed: {exc}") from exc
    return pages


def _build_page_inputs(file_path: Path) -> list[dict]:
    if file_path.suffix.casefold() != ".pdf":
        return [{"page_index": 0, "input": str(file_path), "width": None, "height": None}]
    try:
        import numpy as np
        import pypdfium2 as pdfium
    except Exception as exc:
        raise OCRServiceUnavailableError(f"unable to render PDF before OCR: {exc}") from exc

    try:
        pdf = pdfium.PdfDocument(str(file_path))
        page_inputs = []
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            bitmap = page.render(scale=PDF_RENDER_SCALE, rotation=0)
            image = bitmap.to_pil().convert("RGB")
            page_inputs.append(
                {
                    "page_index": page_index,
                    "input": np.array(image),
                    "width": image.width,
                    "height": image.height,
                }
            )
        return page_inputs
    except Exception as exc:
        raise OCRServiceUnavailableError(f"PDF rendering failed: {exc}") from exc


def _extract_ocr_lines(payload: dict) -> list[dict]:
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
    return lines


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


def _resolve_model_dir(override_dir: str | None, label: str) -> Path | None:
    if not override_dir:
        return None
    model_dir = Path(override_dir)
    config_path = model_dir / "inference.yml"
    if not config_path.exists():
        raise OCRServiceUnavailableError(f"{label} model dir is missing inference.yml: {model_dir}")
    return model_dir


def _configure_paddlex_env() -> None:
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", settings.paddle_model_source)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(settings.paddle_model_dir_path))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
