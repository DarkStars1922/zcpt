from sqlmodel import Session, select

from app.core.award_catalog import load_award_rule_map, load_award_score_map, load_award_tree
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.core.utils import json_dumps
from app.models.award_dict import AwardDict
from app.models.system_config import SystemConfig


def initialize_schema() -> None:
    if settings.auto_create_tables:
        create_db_and_tables()


def seed_initial_data(db: Session) -> None:
    _seed_award_dicts(db)
    _seed_system_configs(db)


def _seed_award_dicts(db: Session) -> None:
    rule_map = load_award_rule_map()
    has_award = db.exec(select(AwardDict.id)).first()
    if has_award:
        _sync_award_rule_metadata(db, rule_map)
        return

    records = []
    for award_uid, payload in load_award_score_map().items():
        rule = rule_map.get(award_uid) or {}
        records.append(
            AwardDict(
                award_uid=award_uid,
                category=rule.get("category"),
                sub_type=rule.get("sub_type"),
                award_name=rule.get("rule_name") or rule.get("rule_path") or f"Award {award_uid}",
                score=rule.get("score", payload["score"]),
                max_score=rule.get("max_score", payload["max_score"]),
            )
        )

    if records:
        db.add_all(records)
        db.commit()


def _sync_award_rule_metadata(db: Session, rule_map: dict[int, dict]) -> None:
    if not rule_map:
        return
    changed = False
    rows = db.exec(select(AwardDict)).all()
    for row in rows:
        row_changed = False
        rule = rule_map.get(row.award_uid)
        if not rule:
            continue
        new_name = rule.get("rule_name") or rule.get("rule_path") or row.award_name
        if new_name and row.award_name != new_name:
            row.award_name = new_name
            row_changed = True
        if not row.category and rule.get("category"):
            row.category = rule["category"]
            row_changed = True
        if not row.sub_type and rule.get("sub_type"):
            row.sub_type = rule["sub_type"]
            row_changed = True
        if float(row.score or 0.0) == 0.0 and rule.get("score") is not None:
            row.score = float(rule["score"])
            row_changed = True
        if float(row.max_score or 0.0) == 0.0 and rule.get("max_score") is not None:
            row.max_score = float(rule["max_score"])
            row_changed = True
        if row_changed:
            db.add(row)
            changed = True
    if changed:
        db.commit()


def _seed_system_configs(db: Session) -> None:
    if db.exec(select(SystemConfig.id)).first():
        return

    defaults = [
        SystemConfig(
            config_key="categories",
            config_value_json=json_dumps(load_award_tree()),
            description="application categories and sub-types",
        ),
        SystemConfig(
            config_key="ai_audit",
            config_value_json=json_dumps(
                {
                    "provider": settings.ai_audit_provider,
                    "fallback_to_manual": settings.ai_audit_fallback_to_manual,
                }
            ),
            description="AI audit runtime configuration",
        ),
        SystemConfig(
            config_key="email",
            config_value_json=json_dumps(
                {
                    "provider": settings.email_provider,
                    "default_from": settings.email_default_from,
                }
            ),
            description="email notification runtime configuration",
        ),
    ]
    db.add_all(defaults)
    db.commit()
