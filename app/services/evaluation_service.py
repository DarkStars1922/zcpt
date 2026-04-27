import logging
import json
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是高校综合测评报告撰写助手。请根据给定分数写一段中文鼓励性综合评价，"
    "语气具体、温和、积极，不编造没有提供的数据。"
)
STORY_SYSTEM_PROMPT = (
    "你是高校学生年度报告H5文案设计师，擅长把真实综测数据写成温柔、克制、"
    "有画面感的中文短句。你必须只使用用户提供的数据，不编造奖项、日期、分数或经历。"
)


def build_report_evaluation(*, radar: dict, allow_llm: bool = True) -> dict:
    placeholder = "综合评价暂未生成"
    base_payload = {
        "title": "综合评价",
        "content": "",
        "placeholder": placeholder,
        "source": "llm",
        "status": "not_configured",
    }
    if not allow_llm:
        return {
            **base_payload,
            "source": "rule",
            "status": "deferred",
            "placeholder": "综合评价正在随星图一起整理，稍后会在这里写下一段专属鼓励。",
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


def build_report_story_copy(
    *,
    student: dict,
    radar: dict,
    story_metrics: dict,
    story_cards: list[dict],
    award_history: list[dict],
) -> dict:
    fallback = {
        "source": "rule",
        "status": "fallback",
        "hero_quote": _fallback_hero_quote(student, story_metrics),
        "ending_text": "",
        "story_cards": story_cards,
    }
    api_url = settings.report_story_llm_api_url or settings.evaluation_llm_api_url
    api_key = settings.report_story_llm_api_key or settings.evaluation_llm_api_key
    if not api_url or not api_key:
        return {**fallback, "status": "not_configured"}

    prompt = _build_story_prompt(
        student=student,
        radar=radar,
        story_metrics=story_metrics,
        story_cards=story_cards,
        award_history=award_history,
    )
    try:
        content = _request_story_copy(prompt, api_url=api_url, api_key=api_key)
        parsed = _extract_json_object(content)
        return _merge_story_copy(parsed, fallback_cards=story_cards, fallback=fallback)
    except Exception as exc:
        logger.warning("report story llm request failed: %s", exc)
        return {**fallback, "status": "failed", "error_message": str(exc)}


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


def _request_story_copy(prompt: str, *, api_url: str, api_key: str) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.report_story_llm_model or settings.evaluation_llm_model,
        "messages": [
            {"role": "system", "content": STORY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": settings.report_story_llm_temperature,
        "max_tokens": settings.report_story_llm_max_tokens,
    }
    with httpx.Client(timeout=settings.report_story_llm_timeout_seconds) as client:
        response = client.post(api_url, headers=headers, json=payload)
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


def _build_story_prompt(*, student: dict, radar: dict, story_metrics: dict, story_cards: list[dict], award_history: list[dict]) -> str:
    score_lines = []
    for category in radar.get("categories") or []:
        score_lines.append(f"{category.get('name')}：{_score(category.get('score'))}/{_score(category.get('max_score'))}")
        for item in category.get("submodules") or []:
            score_lines.append(f"- {item.get('name')}：{_score(item.get('score'))}/{_score(item.get('max_score'))}")
    award_lines = []
    for item in (award_history or [])[:12]:
        award_lines.append(
            f"{item.get('occurred_at') or '-'}｜{item.get('title')}｜{item.get('category_name')}·{item.get('sub_type_name')}｜{_score(item.get('score'))}分"
        )
    card_lines = []
    for card in story_cards:
        card_lines.append(
            f"{card.get('key')}｜{card.get('eyebrow')}｜{card.get('title')}｜数值={card.get('value')}{card.get('unit')}｜原描述={card.get('description')}"
        )
    return (
        "请为学生个人综测H5年度报告生成个性化语录和故事卡文案。\n"
        "输出必须是严格JSON对象，不要使用Markdown，不要解释。\n"
        "只允许改写文案，不允许改变分数、数量、奖项事实、颜色、key、value、unit。\n"
        "语气参考ChatGPT年度总结或B站年度报告：漂亮、优雅、有画面感，但不要夸张和油腻。\n"
        "每张卡的title不超过22个中文字符，description不超过54个中文字符，quote不超过28个中文字符。\n"
        "hero_quote不超过56个中文字符，ending_text不超过90个中文字符。\n"
        "返回结构必须为：\n"
        "{\n"
        '  "hero_quote": "封面短语",\n'
        '  "ending_text": "结尾鼓励语",\n'
        '  "cards": [\n'
        '    {"key": "journey", "eyebrow": "短标签", "title": "标题", "description": "描述", "quote": "一句语录"}\n'
        "  ]\n"
        "}\n\n"
        f"学生：{student.get('name') or '同学'}，班级：{student.get('class_id') or '-'}。\n"
        f"故事指标：{json.dumps(story_metrics, ensure_ascii=False)}\n"
        f"四类八项分数：\n{chr(10).join(score_lines) or '暂无分数'}\n"
        f"奖项历史：\n{chr(10).join(award_lines) or '暂无奖项历史'}\n"
        f"需要改写的卡片：\n{chr(10).join(card_lines)}"
    )


def _extract_json_object(content: str) -> dict:
    if not content:
        raise ValueError("empty llm response")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("llm response must be a json object")
    return payload


def _merge_story_copy(parsed: dict, *, fallback_cards: list[dict], fallback: dict) -> dict:
    raw_cards = parsed.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("llm response missing cards")
    override_by_key = {
        str(item.get("key")): item
        for item in raw_cards
        if isinstance(item, dict) and item.get("key")
    }
    merged_cards = []
    for card in fallback_cards:
        key = str(card.get("key"))
        override = override_by_key.get(key) or {}
        merged = {**card}
        for field, limit in {"eyebrow": 16, "title": 22, "description": 54, "quote": 28}.items():
            value = _clean_text(override.get(field), max_length=limit)
            if value:
                merged[field] = value
        merged_cards.append(merged)
    return {
        "source": "llm",
        "status": "completed",
        "hero_quote": _clean_text(parsed.get("hero_quote"), max_length=56) or fallback["hero_quote"],
        "ending_text": _clean_text(parsed.get("ending_text"), max_length=90) or fallback["ending_text"],
        "story_cards": merged_cards,
    }


def _clean_text(value, *, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text[:max_length]


def _fallback_hero_quote(student: dict, story_metrics: dict) -> str:
    name = student.get("name") or "你"
    term_label = story_metrics.get("term_label") or "这个学期"
    return f"{term_label}，{name}把校园里的努力写成了自己的星轨。"


def _score(value) -> str:
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")
