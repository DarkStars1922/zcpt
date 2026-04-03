from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.v1.router import api_router
from app.core.bootstrap import initialize_schema, seed_initial_data
from app.core.config import settings
from app.core.database import get_engine
from app.core.responses import error_response, success_response
import app.models as models_registry


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ = models_registry
    initialize_schema()
    with Session(get_engine()) as db:
        seed_initial_data(db)
    yield


app = FastAPI(title="Comprehensive Evaluation Platform API", version="1.0.0", lifespan=lifespan)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health_api(request: Request):
    return success_response(
        request=request,
        message="ok",
        data={
            "status": "ok",
            "environment": settings.environment,
            "database_driver": settings.database_url.split("://", 1)[0],
            "redis_enabled": settings.redis_enabled,
            "celery_eager": settings.celery_task_always_eager,
        },
    )


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
        message="invalid request payload",
        error={"reason": str(exc)},
    )
    return JSONResponse(status_code=400, content=payload)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    payload = error_response(
        request=request,
        code=1001,
        message="request validation failed",
        error={"reason": exc.errors()},
    )
    return JSONResponse(status_code=422, content=payload)


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
