from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.applications import router as applications_router
from app.api.v1.endpoints.exports_archives_announcements import (
	router as export_archive_announcement_router,
)
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.reviews import router as reviews_router
from app.api.v1.endpoints.tokens import router as tokens_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(applications_router)
api_router.include_router(export_archive_announcement_router)
api_router.include_router(files_router)
api_router.include_router(reviews_router)
api_router.include_router(tokens_router)
