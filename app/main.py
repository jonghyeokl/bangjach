from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.api import catalog, friends, health, reviews, users
from app.core.config import settings
from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
)
app.include_router(health.router, prefix="/api/v1")
for router in (users.router, catalog.router, reviews.router, friends.router):
    app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {"code": "HTTP_ERROR", "message": str(exc.detail), "details": None}
    )
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo password, token, request body or submitted secrets back to clients/logs.
    details = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력값을 확인하세요.",
                "details": details,
            }
        },
        status_code=422,
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return JSONResponse(
        {
            "error": {
                "code": "CONFLICT",
                "message": "중복된 정보이거나 현재 상태에서 처리할 수 없습니다.",
                "details": None,
            }
        },
        status_code=409,
    )
