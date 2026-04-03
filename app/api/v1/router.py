from fastapi import APIRouter

from app.api.v1.endpoints.ai_audits import router as ai_audits_router
from app.api.v1.endpoints.announcements import router as announcements_router
from app.api.v1.endpoints.appeals import router as appeals_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.archives import router as archives_router
from app.api.v1.endpoints.applications import router as applications_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.reviews import router as reviews_router
from app.api.v1.endpoints.system import router as system_router
from app.api.v1.endpoints.teacher import router as teacher_router
from app.api.v1.endpoints.tokens import router as tokens_router
from app.api.v1.endpoints.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(applications_router)
api_router.include_router(files_router)
api_router.include_router(reviews_router)
api_router.include_router(tokens_router)
api_router.include_router(teacher_router)
api_router.include_router(archives_router)
api_router.include_router(announcements_router)
api_router.include_router(appeals_router)
api_router.include_router(notifications_router)
api_router.include_router(ai_audits_router)
api_router.include_router(system_router)
