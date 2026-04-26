from __future__ import annotations

import re
from datetime import date, datetime, timezone

TERM_PATTERN = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{4})-(?P<part>[12])$")


def current_fill_term_label(reference_time: datetime | None = None) -> str:
    current = reference_time or datetime.now(timezone.utc)
    end_year = current.year if current.month < 9 else current.year + 1
    return f"{end_year - 1}-{end_year}-1"


def parse_term_datetime_range(term: str | None) -> tuple[datetime, datetime] | None:
    if not term:
        return None
    term_text = str(term).strip()
    match = TERM_PATTERN.match(term_text)
    if not match:
        return None

    start_year = int(match.group("start"))
    end_year = int(match.group("end"))
    part = match.group("part")
    if part == "1":
        return (
            datetime(start_year, 9, 1, tzinfo=timezone.utc),
            datetime(end_year, 9, 1, tzinfo=timezone.utc),
        )
    return (
        datetime(end_year, 9, 1, tzinfo=timezone.utc),
        datetime(end_year + 1, 1, 1, tzinfo=timezone.utc),
    )

def format_term_label(term: str | None) -> str:
    if not term:
        return ""
    match = TERM_PATTERN.match(str(term).strip())
    if not match:
        return str(term)
    season = "秋季填报学期" if match.group("part") == "1" else "非填报学期"
    return f"{match.group('start')}-{match.group('end')}学年{season}"


def parse_term_date_range(term: str | None) -> tuple[date, date] | None:
    values = parse_term_datetime_range(term)
    if not values:
        return None
    start_at, end_at = values
    return start_at.date(), end_at.date()


def apply_datetime_term_filter(stmt, column, term: str | None):
    values = parse_term_datetime_range(term)
    if not values:
        return stmt
    start_at, end_at = values
    return stmt.where(column >= start_at, column < end_at)


def apply_date_term_filter(stmt, column, term: str | None):
    values = parse_term_date_range(term)
    if not values:
        return stmt
    start_at, end_at = values
    return stmt.where(column >= start_at, column < end_at)


def datetime_in_term(value: datetime | None, term: str | None) -> bool:
    values = parse_term_datetime_range(term)
    if not values or value is None:
        return True
    start_at, end_at = values
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return start_at <= current < end_at


def date_in_term(value: date | None, term: str | None) -> bool:
    values = parse_term_date_range(term)
    if not values or value is None:
        return True
    start_at, end_at = values
    return start_at <= value < end_at
