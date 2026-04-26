SCORE_RULE_VERSION = "v2_four_categories_two_subtypes"

SCORE_CATEGORY_RULES: dict[str, dict] = {
    "physical_mental": {
        "name": "身心素养",
        "max_score": 15.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 9.0},
            "achievement": {"name": "成果性评价", "max_score": 6.0},
        },
    },
    "art": {
        "name": "文艺素养",
        "max_score": 15.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 9.0},
            "achievement": {"name": "成果性评价", "max_score": 6.0},
        },
    },
    "labor": {
        "name": "劳动素养",
        "max_score": 25.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 15.0},
            "achievement": {"name": "成果性评价", "max_score": 10.0},
        },
    },
    "innovation": {
        "name": "创新素养",
        "max_score": 45.0,
        "sub_types": {
            "basic": {"name": "基础素养", "max_score": 5.0},
            "achievement": {"name": "突破提升", "max_score": 40.0},
        },
    },
}

SCORE_CATEGORY_KEYS = tuple(SCORE_CATEGORY_RULES.keys())
SCORE_SUB_TYPE_KEYS = ("basic", "achievement")
SCORE_SUB_FIELD_KEYS = tuple(
    f"{category}_{sub_type}"
    for category in SCORE_CATEGORY_KEYS
    for sub_type in SCORE_SUB_TYPE_KEYS
)
SCORE_CATEGORY_FIELD_KEYS = tuple(f"{category}_score" for category in SCORE_CATEGORY_KEYS)
SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS = tuple(
    f"{category}_achievement_overflow"
    for category in SCORE_CATEGORY_KEYS
)


def build_category_options() -> list[dict]:
    return [
        {
            "category": category,
            "name": rule["name"],
            "max_score": rule["max_score"],
            "children": [
                {
                    "code": sub_type,
                    "name": sub_rule["name"],
                    "max_score": sub_rule["max_score"],
                }
                for sub_type, sub_rule in rule["sub_types"].items()
            ],
        }
        for category, rule in SCORE_CATEGORY_RULES.items()
    ]


def is_valid_score_category(category: str | None, sub_type: str | None) -> bool:
    if not category or not sub_type:
        return False
    return category in SCORE_CATEGORY_RULES and sub_type in SCORE_CATEGORY_RULES[category]["sub_types"]
