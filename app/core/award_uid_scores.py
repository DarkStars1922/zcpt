"""后端奖项 UID 分数字典（由前端 award-dicts.js 提取并落地为 JSON）。"""

from __future__ import annotations

import json
from pathlib import Path

AWARD_SCORE_RULE_VERSION = "2026-02-25-v1"

_MAP_PATH = Path(__file__).with_name("award_uid_score_map.json")
with _MAP_PATH.open("r", encoding="utf-8") as _file:
    _raw_map: dict[str, dict[str, float | str | None]] = json.load(_file)

AWARD_UID_SCORE_MAP: dict[int, dict[str, float | str | None]] = {
    int(uid): {"score": item.get("score"), "max_score": item.get("maxScore")}
    for uid, item in _raw_map.items()
}

AWARD_UID_SCORE_LIST: list[dict[str, float | str | None | int]] = [
    {"uid": uid, "score": item["score"], "max_score": item["max_score"]}
    for uid, item in sorted(AWARD_UID_SCORE_MAP.items(), key=lambda pair: pair[0])
]

AWARD_UID_INDEX = {item["uid"]: item for item in AWARD_UID_SCORE_LIST}
