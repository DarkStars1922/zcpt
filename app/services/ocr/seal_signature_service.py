from __future__ import annotations

import re
from typing import Any


SEAL_HINTS = ("章", "印", "专用章", "公章", "盖章")
ORG_SEAL_HINTS = (
    "大学",
    "学院",
    "学校",
    "委员会",
    "组委会",
    "协会",
    "中心",
    "办公室",
    "教务",
    "学生工作",
    "竞赛",
    "公司",
    "研究院",
    "实验室",
    "厅",
    "局",
)
SIGNATURE_HINTS = ("签名", "签字", "落款", "负责人", "审核", "经办", "辅导员", "老师", "日期", "年", "月", "日")
DATE_PATTERN = re.compile(r"(?:20\d{2}|19\d{2})\s*[年./-]\s*\d{1,2}\s*(?:[月./-]\s*\d{1,2}\s*日?)?")


def extract_seal_and_signature(
    *,
    ocr_pages: list[dict],
    layout_pages: list[dict],
    uploader_name: str | None = None,
    seal_score_threshold: float = 0.4,
) -> dict:
    seal_items = _extract_seal_items(
        ocr_pages=ocr_pages,
        layout_pages=layout_pages,
        seal_score_threshold=seal_score_threshold,
    )
    signature_items = _extract_signature_items(
        ocr_pages=ocr_pages,
        seal_items=seal_items,
        uploader_name=uploader_name,
    )
    return {
        "seal": {"detected": bool(seal_items), "items": seal_items},
        "signature": {"detected": bool(signature_items), "items": signature_items},
    }


def _extract_seal_items(*, ocr_pages: list[dict], layout_pages: list[dict], seal_score_threshold: float) -> list[dict]:
    layout_by_page = {str(item.get("page_index")): item for item in layout_pages}
    results: list[dict] = []
    for page in ocr_pages:
        page_index = page.get("page_index")
        layout = layout_by_page.get(str(page_index), {})
        seal_boxes = [
            item
            for item in layout.get("boxes", [])
            if item.get("label") == "seal" and float(item.get("score") or 0.0) >= seal_score_threshold
        ]
        if not seal_boxes:
            keyword_lines = [
                line["text"] for line in page.get("lines", []) if _looks_like_seal_text(line.get("text") or "")
            ]
            if keyword_lines:
                results.append(
                    {
                        "page_index": page_index,
                        "box": None,
                        "score": None,
                        "texts": keyword_lines[:5],
                        "source": "text_keyword",
                    }
                )
            continue

        for item in seal_boxes:
            coordinate = item.get("coordinate")
            texts = []
            for line in page.get("lines", []):
                if _line_hits_region(line.get("box"), coordinate):
                    texts.append(line["text"])
            results.append(
                {
                    "page_index": page_index,
                    "box": coordinate,
                    "score": item.get("score"),
                    "texts": texts[:8],
                    "source": "layout",
                }
            )
    return results


def _extract_signature_items(*, ocr_pages: list[dict], seal_items: list[dict], uploader_name: str | None) -> list[dict]:
    seal_boxes_by_page: dict[str, list[list[float]]] = {}
    for item in seal_items:
        box = item.get("box")
        if box:
            seal_boxes_by_page.setdefault(str(item.get("page_index")), []).append(box)

    results: list[dict] = []
    for page in ocr_pages:
        page_index = page.get("page_index")
        page_height = float(page.get("height") or 0.0)
        if page_height <= 0:
            page_height = _estimate_page_height(page.get("lines", []))
        for line in page.get("lines", []):
            text = line.get("text") or ""
            if not text:
                continue
            if not _looks_like_signature_candidate(
                text=text,
                box=line.get("box"),
                page_height=page_height,
                seal_boxes=seal_boxes_by_page.get(str(page_index), []),
                uploader_name=uploader_name,
            ):
                continue
            results.append(
                {
                    "page_index": page_index,
                    "text": text,
                    "box": line.get("box"),
                    "score": line.get("score"),
                }
            )
    return results[:8]


def _looks_like_signature_candidate(
    *,
    text: str,
    box: Any,
    page_height: float,
    seal_boxes: list[list[float]],
    uploader_name: str | None,
) -> bool:
    text = text.strip()
    if not text:
        return False
    bottom_ratio = _box_bottom_ratio(box, page_height)
    near_bottom = bottom_ratio is not None and bottom_ratio >= 0.62
    near_seal = any(_line_hits_region(box, seal_box, expand=48.0) for seal_box in seal_boxes)
    has_hint = any(hint in text for hint in SIGNATURE_HINTS)
    has_date = bool(DATE_PATTERN.search(text))
    has_uploader = bool(uploader_name and uploader_name in text)
    is_short = len(text) <= 24
    if has_hint and (near_bottom or near_seal or is_short):
        return True
    if has_date and (near_bottom or near_seal or is_short):
        return True
    if has_uploader and (near_bottom or near_seal):
        return True
    return near_bottom and is_short


def _looks_like_seal_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(hint in stripped for hint in SEAL_HINTS):
        return True
    if len(stripped) > 40:
        return False
    return any(hint in stripped for hint in ORG_SEAL_HINTS)


def _box_bottom_ratio(box: Any, page_height: float) -> float | None:
    if not box or page_height <= 0:
        return None
    rect = _box_to_rect(box)
    if not rect:
        return None
    _, _, _, bottom = rect
    return bottom / page_height


def _estimate_page_height(lines: list[dict]) -> float:
    bottoms = []
    for line in lines:
        rect = _box_to_rect(line.get("box"))
        if rect:
            bottoms.append(rect[3])
    return max(bottoms, default=0.0)


def _line_hits_region(box: Any, region: Any, *, expand: float = 0.0) -> bool:
    line_rect = _box_to_rect(box)
    region_rect = _box_to_rect(region)
    if not line_rect or not region_rect:
        return False
    left, top, right, bottom = region_rect
    region_rect = [left - expand, top - expand, right + expand, bottom + expand]
    return _rect_intersection_ratio(line_rect, region_rect) > 0.25


def _rect_intersection_ratio(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    first_area = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    return intersection / first_area


def _box_to_rect(box: Any) -> list[float] | None:
    if not box:
        return None
    if isinstance(box, list) and len(box) == 4 and all(isinstance(item, (int, float)) for item in box):
        return [float(box[0]), float(box[1]), float(box[2]), float(box[3])]
    if isinstance(box, list):
        xs = []
        ys = []
        for point in box:
            if isinstance(point, list) and len(point) >= 2:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
        if xs and ys:
            return [min(xs), min(ys), max(xs), max(ys)]
    return None
