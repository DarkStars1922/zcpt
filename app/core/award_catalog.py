import ast
import json
from pathlib import Path
from typing import Any

from app.core.constants import CATEGORY_OPTIONS


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_award_score_map() -> dict[int, dict[str, float]]:
    score_map_path = _repo_root() / "app" / "data" / "award_score_map.json"
    if not score_map_path.exists():
        return {}

    with score_map_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)

    result: dict[int, dict[str, float]] = {}
    for key, value in raw.items():
        try:
            uid = int(key)
        except ValueError:
            continue

        score = _coerce_score(value.get("score", 0.0))
        max_score = _coerce_score(value.get("maxScore", value.get("max_score", score)))
        result[uid] = {
            "score": score,
            "max_score": max(score, max_score),
        }
    return result


def load_award_tree() -> list[dict[str, Any]]:
    tree_path = _repo_root() / "app" / "data" / "award_tree.json"
    if not tree_path.exists():
        return CATEGORY_OPTIONS
    with tree_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _coerce_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0.0
        try:
            return float(stripped)
        except ValueError:
            try:
                return float(_safe_eval_score_expr(stripped))
            except Exception:
                return 0.0
    return 0.0


def _safe_eval_score_expr(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    return float(_eval_node(tree.body))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id.lower() == "x":
        return 1.0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left / right
    raise ValueError(f"unsupported score expression: {ast.dump(node)}")
