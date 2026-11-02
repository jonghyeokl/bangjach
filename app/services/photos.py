"""Private object storage; only photos attached to public reviews are served."""

import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, update

from app.core.config import settings
from app.core.errors import fail
from app.domain.models import ReviewPhoto, now

MAX_BYTES = 8 * 1024 * 1024


def normalize(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError()
                if original.width * original.height > 25_000_000:
                    raise ValueError()
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1600, 1600))
                image = image.convert("RGB")
                output = BytesIO()
                image.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        fail(422, "INVALID_PHOTO", "사진은 2,500만 화소 이하의 JPEG·PNG·WebP 파일로 첨부해주세요.")


def bucket():
    from google.cloud import storage

    return storage.Client().bucket(settings.review_photo_bucket)


def write(key: str, data: bytes):
    if settings.review_photo_bucket:
        bucket().blob(key).upload_from_string(data, content_type="image/jpeg", timeout=30)
    else:
        if settings.environment == "production":
            fail(503, "PHOTO_STORAGE_UNAVAILABLE", "사진 저장소가 준비되지 않았어요.")
        target = Path(settings.review_photo_local_dir) / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def read(key: str) -> bytes:
    if settings.review_photo_bucket:
        return bucket().blob(key).download_as_bytes(timeout=30)
    if settings.environment == "production":
        fail(503, "PHOTO_STORAGE_UNAVAILABLE", "사진 저장소가 준비되지 않았어요.")
    return (Path(settings.review_photo_local_dir) / key).read_bytes()


def remove(key: str):
    if settings.review_photo_bucket:
        from google.api_core.exceptions import NotFound

        try:
            bucket().blob(key).delete(timeout=30)
        except NotFound:
            pass
    else:
        if settings.environment == "production":
            raise RuntimeError("Photo bucket is not configured")
        (Path(settings.review_photo_local_dir) / key).unlink(missing_ok=True)


async def attach(db, user_id, review_id, ids):
    # Lock in a fixed order: one staged photo must never attach to two reviews.
    rows = (
        await db.scalars(
            select(ReviewPhoto)
            .where(ReviewPhoto.id.in_(ids))
            .order_by(ReviewPhoto.id)
            .with_for_update()
        )
    ).all()
    if len(rows) != len(ids) or any(
        p.user_id != user_id or p.review_id not in (None, review_id) for p in rows
    ):
        fail(422, "INVALID_PHOTO", "본인이 올린 사용 가능한 사진만 첨부할 수 있습니다.")
    await db.execute(
        update(ReviewPhoto)
        .where(ReviewPhoto.review_id == review_id, ReviewPhoto.id.not_in(ids))
        .values(review_id=None, updated_dt=now())
    )
    positions = {photo_id: index for index, photo_id in enumerate(ids)}
    for photo in rows:
        photo.review_id = review_id
        photo.position = positions[photo.id]
    await db.flush()
