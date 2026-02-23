from fastapi import Request


def success_response(*, request: Request, data: dict | None = None, message: str = "ok") -> dict:
    return {
        "code": 0,
        "message": message,
        "data": data or {},
        "request_id": getattr(request.state, "request_id", None),
    }


def error_response(*, request: Request, code: int, message: str, error: dict | None = None) -> dict:
    body = {
        "code": code,
        "message": message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if error is not None:
        body["error"] = error
    return body
