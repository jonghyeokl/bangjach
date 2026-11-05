# 로컬 실행 명령어

2026-11-05부터 repo 안의 `data/bangjach.db`(SQLite)와 `data/photos`를 직접 사용한다. 별도 DB 서버·프록시·복원은 필요 없다.

## 1. 백엔드

```bash
cd /Users/jonghyeok/bangjach/bangjach
source .venv/bin/activate
unset DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env`: `DATABASE_URL=sqlite+aiosqlite:///./data/bangjach.db`, `ENVIRONMENT=development`, `REVIEW_PHOTO_BUCKET`은 빈 값, `REVIEW_PHOTO_LOCAL_DIR=data/photos`. JWT·관리자 설정은 유지한다. 실제 `.env`는 Git에 넣지 않는다.

## 리뷰 AI 분석

백엔드 `.env`에 `OPENAI_API_KEY=발급받은키` 설정 후 서버 재시작. 기본 모델은 `gpt-4.1-mini`. [API 키 발급](https://platform.openai.com/api-keys). API 키는 앱에 넣지 않는다.

## 2. 앱 — 새 터미널

```bash
cd /Users/jonghyeok/bangjach/bangjach-app
source ../dev-env.sh
npm run start:local
```

휴대폰과 Mac을 같은 Wi-Fi에 연결하고 Expo Go로 QR을 연다. 실행할 때 Mac의 IP를 자동으로 API 주소에 적용한다. 직접 지정하려면 `LOCAL_API_HOST=컴퓨터IP npm run start:local`.
백엔드와 컴퓨터가 켜져 있어야 한다. 웹 개발 시 해당 출처를 백엔드 `CORS_ORIGINS`에도 추가한다.

## DB 확인·통계 갱신

```bash
sqlite3 data/bangjach.db ".tables"
python scripts/refresh_statistics.py
```

이 Mac의 다른 Codex 채팅에서도 **“통계 갱신해줘”**로 실행 가능. 스킬이 바로 보이지 않으면 Codex를 다시 열고 `$bangjach-statistics` 사용.

DB 도구에서는 SQLite를 선택하고 `data/bangjach.db` 파일을 연다. 접속 주소·사용자명·DB 비밀번호는 없다.

## 작업 후 GitHub 저장

각 저장소에서 관련 검사 후 변경 파일만 선택한다.

```bash
git add <변경한 파일>
git commit -m 'feat/short summary'
git push origin main
```

오류 수정은 `fix/short summary`. 이제 push는 소스 저장·CI 실행이며 운영 자동 배포 트리거는 삭제했다.

## GitHub의 DB 데이터

`data/bangjach.db`는 백엔드가 실제 사용하는 DB이며 전체 데이터를 포함한다. 사진은 `data/photos`. DB 변경도 반영하려면 서버·정기 작업·DB 도구를 종료한 뒤 아래처럼 저장한다. 별도 export/import는 하지 않는다.

```bash
git add data/bangjach.db data/photos
git commit -m 'feat/update database'
git push origin main
```

DB 파일은 자동 병합하지 않는다. 다른 컴퓨터의 DB로 교체하기 전에는 현재 파일을 별도 백업한다.

## 이전 기록·백업

- 카페 67개·테마 100개·사용자·로그인 세션: 모든 테이블 행 수와 UTC 기준 해시 비교 완료.
- SQLite 이전: 전체 테이블 행 수·값 비교, 외래키·무결성 검증. 사진 100개는 `data/photos/themes`에 보관.
- PostgreSQL 원본은 `.local/postgres`에 보존하고 서버는 중지했다. 이전 직전 백업은 `../backups/2026-11-05-sqlite-migration/`.
- 이전 백업: `../backups/2026-11-05-local-migration/postgres-public.dump`. 실제 데이터·비밀값이 들어 있는 백업과 `.uploads`는 Git에 올리지 않는다.
- Cloud SQL·사진 버킷·Cloud Scheduler에 이어 Cloud Run 서비스/정기 작업, Cloud Build 트리거, Artifact Registry 이미지 저장소, 배포 소스 버킷도 2026-11-05 삭제 완료.
- 삭제 후 해당 리소스 목록이 모두 비어 있음을 확인했다. 로컬 API에서 테마 100개 및 사진 조회 정상.
- 배포 설정·소스 ZIP 백업: `../backups/2026-11-05-cloud-cleanup/`. 설정에 비밀값이 포함될 수 있으므로 Git에 올리지 않는다.
- 프로젝트·결제 내역·기본 로그는 유지한다. 이미 발생한 사용료는 이후 청구될 수 있다.
- 재배포하려면 클라우드 리소스와 배포 트리거를 새로 구성한다. 과거 배포·DB 이전 기록과 `cloudbuild.yaml`은 Git에 남아 있다.
