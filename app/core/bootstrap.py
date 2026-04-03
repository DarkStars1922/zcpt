from sqlmodel import Session, select

from app.core.award_catalog import load_award_score_map, load_award_tree
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
    has_award = db.exec(select(AwardDict.id)).first()
    if has_award:
        return

    records = []
    for award_uid, payload in load_award_score_map().items():
        records.append(
            AwardDict(
                award_uid=award_uid,
                category=None,
                sub_type=None,
                award_name=f"Award {award_uid}",
                score=payload["score"],
                max_score=payload["max_score"],
            )
        )

    if records:
        db.add_all(records)
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
