# 복원용 카페·테마 데이터

현재 로컬 DB에서 내보낸 카페 67개·테마 100개와 테마 사진 100개다. 기존 빠방 테스트 데이터 수집 결과를 사용한다. 사업장 정보와 테마 소개를 포함한다.

- `catalog.sql`: `cafe`, `theme` 테이블 데이터만 포함. 스키마는 Alembic으로 생성한다.
- `photos/themes/`: 테마 사진. 복원 시 `.uploads/review-photos/themes/`로 복사한다.
- `manifest.json`: 개수 및 파일 SHA-256 검증값.
- 실제 계정·전화번호·비밀번호 해시·로그인 세션·리뷰·친구 관계는 포함하지 않는다. 카페의 공개 전화번호는 포함한다.

백엔드 폴더에서 빈 DB에 복원:

```bash
source .venv/bin/activate
unset DATABASE_URL
alembic upgrade head
python scripts/catalog_data.py import
python -m app.jobs.maintenance
```

기존 카페·테마가 있으면 덮어쓰지 않고 중단한다. 실제 로컬 DB는 이미 데이터가 있으므로 다시 복원할 필요 없다. 복원 후 앱에서 계정을 새로 생성한다.

카페·테마 변경을 GitHub 데이터에 반영하려면:

```bash
python scripts/catalog_data.py export
git diff -- data/catalog
```

실제 DB 변경이 GitHub에 자동 반영되지는 않는다. 내보낸 파일을 검토한 후 commit·push한다. 실행 중인 PostgreSQL 파일(`.local/postgres`)과 `.env`는 올리지 않는다.
