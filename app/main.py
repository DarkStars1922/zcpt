from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.database import Base, engine
from app.core.responses import error_response
import app.models as models_registry


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ = models_registry
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Comprehensive Evaluation Platform API", version="1.0.0", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id")
    if not request_id:
        import uuid

        request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    payload = error_response(
        request=request,
        code=1001,
        message="参数校验失败",
        error={"reason": str(exc)},
    )
    return JSONResponse(status_code=400, content=payload)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        payload = error_response(
            request=request,
            code=detail["code"],
            message=detail["message"],
            error=detail.get("error"),
        )
    else:
        payload = error_response(request=request, code=1000, message=str(detail))
    return JSONResponse(status_code=exc.status_code, content=payload)
