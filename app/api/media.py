from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.core.errors import fail
from app.core.security import DB, CurrentUser, Identity
from app.domain.models import ReviewPhoto, Theme
from app.domain.responses import PhotoResponse
from app.services import photos
from app.services.limits import limit
from app.services.privacy import check_visibility

router = APIRouter(tags=["photos"])


@router.get("/media/v1/theme-photos/{theme_id}")
async def theme_photo(theme_id: UUID, db: DB):
    row = await db.get(Theme, theme_id)
    if not row or row.image_url != f"/media/v1/theme-photos/{theme_id}":
        fail(404, "PHOTO_NOT_FOUND", "사진을 찾을 수 없습니다.")
    try:
        data = await run_in_threadpool(photos.read, f"themes/{theme_id}.jpg")
    except Exception:
        fail(503, "PHOTO_UNAVAILABLE", "사진을 불러오지 못했어요.")
    return Response(
        data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/media/v1/review-photos", status_code=201, response_model=PhotoResponse)
async def upload(request: Request, db: DB, user: CurrentUser):
    await limit(db, "photo:" + str(user.id), 30)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > photos.MAX_BYTES:
            fail(413, "PHOTO_TOO_LARGE", "사진 한 장은 8MB 이하여야 합니다.")
    normalized = await run_in_threadpool(photos.normalize, bytes(data))
    photo_id = uuid4()
    key = f"reviews/{photo_id}.jpg"
    try:
        await run_in_threadpool(photos.write, key, normalized)
    except HTTPException:
        raise
    except Exception:
        fail(503, "PHOTO_UPLOAD_FAILED", "사진을 저장하지 못했어요. 잠시 후 다시 시도해주세요.")
    row = ReviewPhoto(id=photo_id, user_id=user.id, object_key=key)
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await run_in_threadpool(photos.remove, key)
        raise
    return {"id": photo_id, "url": f"/media/v1/review-photos/{photo_id}"}


@router.get("/media/v1/review-photos/{photo_id}")
async def download(photo_id: UUID, db: DB, who: Identity):
    row = await db.get(ReviewPhoto, photo_id)
    if not row or row.review_id is None:
        fail(404, "PHOTO_NOT_FOUND", "사진을 찾을 수 없습니다.")
    await check_visibility(db, who[0].id if who else None, row.user_id)
    try:
        data = await run_in_threadpool(photos.read, row.object_key)
    except Exception:
        fail(503, "PHOTO_UNAVAILABLE", "사진을 불러오지 못했어요.")
    return Response(
        data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
