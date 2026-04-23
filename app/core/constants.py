ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMIN = "admin"

VALID_ROLES = {ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN}
VIEWABLE_ROLES = {ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN}
MANAGE_REVIEW_ROLES = {ROLE_TEACHER, ROLE_ADMIN}

APPLICATION_STATUS_PENDING_AI = "pending_ai"
APPLICATION_STATUS_AI_ABNORMAL = "ai_abnormal"
APPLICATION_STATUS_PENDING_REVIEW = "pending_review"
APPLICATION_STATUS_APPROVED = "approved"
APPLICATION_STATUS_REJECTED = "rejected"
APPLICATION_STATUS_ARCHIVED = "archived"
APPLICATION_STATUS_WITHDRAWN = "withdrawn"

EDITABLE_APPLICATION_STATUSES = {
    APPLICATION_STATUS_PENDING_AI,
    APPLICATION_STATUS_AI_ABNORMAL,
    APPLICATION_STATUS_PENDING_REVIEW,
}
REVIEWER_REVIEWABLE_STATUSES = {
    APPLICATION_STATUS_PENDING_REVIEW,
    APPLICATION_STATUS_AI_ABNORMAL,
}
TEACHER_RECHECKABLE_STATUSES = {
    APPLICATION_STATUS_PENDING_REVIEW,
    APPLICATION_STATUS_AI_ABNORMAL,
    APPLICATION_STATUS_APPROVED,
    APPLICATION_STATUS_REJECTED,
}
SCORE_INCLUDED_STATUSES = {
    APPLICATION_STATUS_PENDING_AI,
    APPLICATION_STATUS_PENDING_REVIEW,
    APPLICATION_STATUS_APPROVED,
    APPLICATION_STATUS_ARCHIVED,
}

EMAIL_STATUS_QUEUED = "queued"
EMAIL_STATUS_SUCCESS = "success"
EMAIL_STATUS_FAILED = "failed"
EMAIL_STATUS_MOCK_SENT = "mock_sent"

EXPORT_STATUS_QUEUED = "queued"
EXPORT_STATUS_RUNNING = "running"
EXPORT_STATUS_COMPLETED = "completed"
EXPORT_STATUS_FAILED = "failed"

ANNOUNCEMENT_STATUS_ACTIVE = "active"
ANNOUNCEMENT_STATUS_CLOSED = "closed"

APPEAL_STATUS_PENDING = "pending"
APPEAL_STATUS_PROCESSED = "processed"

REVIEWER_TOKEN_STATUS_PENDING = "pending"
REVIEWER_TOKEN_STATUS_ACTIVE = "active"
REVIEWER_TOKEN_STATUS_REVOKED = "revoked"
REVIEWER_TOKEN_STATUS_EXPIRED = "expired"

CATEGORY_OPTIONS = [
    {
        "category": "physical_mental",
        "name": "身心素养",
        "children": [
            {"code": "basic", "name": "基础性评价"},
            {"code": "achievement", "name": "成果性评价"},
        ],
    },
    {
        "category": "art",
        "name": "文艺素养",
        "children": [
            {"code": "basic", "name": "基础性评价"},
            {"code": "achievement", "name": "成果性评价"},
        ],
    },
    {
        "category": "labor",
        "name": "劳动素养",
        "children": [
            {"code": "basic", "name": "基础性评价"},
            {"code": "achievement", "name": "成果性评价"},
        ],
    },
    {
        "category": "innovation",
        "name": "创新素养",
        "children": [
            {"code": "basic", "name": "基础素养"},
            {"code": "achievement", "name": "突破提升"},
        ],
    },
]

CLASS_GRADE_MAP = {
    301: 2023,
    302: 2023,
    303: 2023,
}
