from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.errors import ServiceError
from app.services.file_service import delete_file, get_file_metadata, get_file_path_for_user, save_upload_file

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file_api(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        metadata = await save_upload_file(db, user, file)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="upload success", data=metadata)


@router.get("/{file_id}")
def get_file_api(
    request: Request,
    file_id: str,
    raw: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        accept = (request.headers.get("accept") or "").lower()
        wants_json = (
            not raw
            and "application/json" in accept
            and "text/html" not in accept
            and "application/xhtml+xml" not in accept
        )
        if wants_json:
            metadata = get_file_metadata(db, user, file_id)
            return success_response(request=request, message="fetch success", data=metadata)
        file_path = get_file_path_for_user(db, user, file_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return FileResponse(path=file_path)


@router.get("/{file_id}/url")
def get_file_url_api(
    request: Request,
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        get_file_metadata(db, user, file_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data={"url": f"/api/v1/files/{file_id}"})


@router.delete("/{file_id}")
def delete_file_api(
    request: Request,
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_file(db, user, file_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="delete success", data={})
