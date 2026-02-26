from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.api.v1.router import api_router
from app.core.database import Base, engine
from app.core.responses import error_response
import app.models as models_registry


def _ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    if "comprehensive_apply" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("comprehensive_apply")}
    migration_sql_by_column = {
        "award_type": "ALTER TABLE comprehensive_apply ADD COLUMN award_type VARCHAR(64) NOT NULL DEFAULT ''",
        "award_level": "ALTER TABLE comprehensive_apply ADD COLUMN award_level VARCHAR(64) NOT NULL DEFAULT ''",
        "award_uid": "ALTER TABLE comprehensive_apply ADD COLUMN award_uid INTEGER NOT NULL DEFAULT 0",
        "score": "ALTER TABLE comprehensive_apply ADD COLUMN score FLOAT",
        "comment": "ALTER TABLE comprehensive_apply ADD COLUMN comment TEXT",
        "score_rule_version": "ALTER TABLE comprehensive_apply ADD COLUMN score_rule_version VARCHAR(32)",
        "version": "ALTER TABLE comprehensive_apply ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
        "is_deleted": "ALTER TABLE comprehensive_apply ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0",
        "updated_at": "ALTER TABLE comprehensive_apply ADD COLUMN updated_at DATETIME",
        "deleted_at": "ALTER TABLE comprehensive_apply ADD COLUMN deleted_at DATETIME",
    }

    with engine.begin() as connection:
        for column_name, ddl_sql in migration_sql_by_column.items():
            if column_name not in columns:
                connection.execute(text(ddl_sql))

        if "award_type" in columns and "category" in columns:
            connection.execute(
                text(
                    "UPDATE comprehensive_apply "
                    "SET award_type = category "
                    "WHERE (award_type IS NULL OR award_type = '') AND category IS NOT NULL"
                )
            )

        if "award_level" in columns and "sub_type" in columns:
            connection.execute(
                text(
                    "UPDATE comprehensive_apply "
                    "SET award_level = sub_type "
                    "WHERE (award_level IS NULL OR award_level = '') AND sub_type IS NOT NULL"
                )
            )

        if "input_score" in columns:
            connection.execute(
                text(
                    "UPDATE comprehensive_apply "
                    "SET score = input_score "
                    "WHERE score IS NULL AND input_score IS NOT NULL"
                )
            )

        if "item_score" in columns:
            connection.execute(
                text(
                    "UPDATE comprehensive_apply "
                    "SET score = item_score "
                    "WHERE score IS NULL AND item_score IS NOT NULL"
                )
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ = models_registry
    Base.metadata.create_all(engine)
    _ensure_schema_compatibility()
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
