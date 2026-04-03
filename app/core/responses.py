from typing import Any

from fastapi import Request


def success_response(*, request: Request, data: Any = None, message: str = "ok") -> dict:
    return {
        "code": 0,
        "message": message,
        "data": {} if data is None else data,
        "request_id": getattr(request.state, "request_id", None),
    }


def error_response(*, request: Request, code: int, message: str, error: Any = None) -> dict:
    body = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if error is not None:
        body["error"] = error
    return body
