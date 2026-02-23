from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.file_service import FileError, get_file_path, save_upload_file

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file_api(
    request: Request,
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    try:
        metadata = await save_upload_file(file)
    except FileError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    base_url = str(request.base_url).rstrip("/")
    file_url = f"{base_url}/api/v1/files/{metadata['file_id']}"
    return success_response(
        request=request,
        message="上传成功",
        data={
            "file_id": metadata["file_id"],
            "filename": metadata["filename"],
            "content_type": metadata["content_type"],
            "size": metadata["size"],
            "url": file_url,
        },
    )


@router.get("/{file_id}")
def get_file_api(request: Request, file_id: str):
    try:
        file_path = get_file_path(file_id)
    except FileError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return FileResponse(path=file_path)
