import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是高校综合测评报告撰写助手。请根据给定分数写一段中文鼓励性综合评价，"
    "语气具体、温和、积极，不编造没有提供的数据。"
)


def build_report_evaluation(*, radar: dict) -> dict:
    placeholder = "综合评价暂未生成"
    base_payload = {
        "title": "综合评价",
        "content": "",
        "placeholder": placeholder,
        "source": "llm",
        "status": "not_configured",
    }
    if not settings.evaluation_llm_api_url or not settings.evaluation_llm_api_key:
        return base_payload

    prompt = _build_evaluation_prompt(radar)
    try:
        content = _request_evaluation(prompt)
    except Exception as exc:  # keep the report available even if the provider is unavailable
        logger.warning("evaluation llm request failed: %s", exc)
        return {**base_payload, "status": "failed", "error_message": str(exc)}

    if not content:
        return {**base_payload, "status": "empty"}
    return {
        **base_payload,
        "content": content,
        "status": "completed",
    }


def _request_evaluation(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.evaluation_llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.evaluation_llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": settings.evaluation_llm_temperature,
        "max_tokens": settings.evaluation_llm_max_tokens,
    }
    with httpx.Client(timeout=settings.evaluation_llm_timeout_seconds) as client:
        response = client.post(settings.evaluation_llm_api_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_content(data).strip()


def _extract_content(data: dict) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content") or first.get("text")
        if isinstance(content, str):
            return content
    content = data.get("content")
    if isinstance(content, str):
        return content
    nested_data = data.get("data")
    if isinstance(nested_data, dict) and isinstance(nested_data.get("content"), str):
        return nested_data["content"]
    return ""


def _build_evaluation_prompt(radar: dict) -> str:
    rows = []
    for category in radar.get("categories") or []:
        rows.append(f"{category.get('name')}：{_score(category.get('score'))}/{_score(category.get('max_score'))}分")
        for item in category.get("submodules") or []:
            overflow_text = ""
            if item.get("sub_type") == "achievement" and float(item.get("overflow_score") or 0) > 0:
                overflow_text = f"，含溢出后{_score(item.get('score_with_overflow'))}分"
            rows.append(
                f"- {category.get('name')}·{item.get('name')}："
                f"{_score(item.get('score'))}/{_score(item.get('max_score'))}分{overflow_text}"
            )
    score_text = "\n".join(rows) or "暂无分数数据"
    return (
        "请根据以下四大类与八个小模块评分，写一段100到160字的中文综合评价。\n"
        "评价必须说明：哪一方面表现较好；哪一方面、哪些小模块还需要进步；"
        "结尾使用类似“新的学期继续加油”的鼓励语。\n"
        "不要使用列表，不要输出标题，不要提及JSON、接口或模型。\n\n"
        f"评分数据：\n{score_text}"
    )


def _score(value) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")
