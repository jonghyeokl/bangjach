# 로컬 실행 명령어

2026-11-05부터 로컬 PostgreSQL 18과 로컬 사진 저장소를 사용한다. 클라우드 DB 프록시는 필요 없다.

## 1. 백엔드

```bash
cd /Users/jonghyeok/bangjach/bangjach
brew services start postgresql@18
source .venv/bin/activate
unset DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`.env`: `DATABASE_URL`은 `127.0.0.1:5432/bangjach`, `ENVIRONMENT=development`, `REVIEW_PHOTO_BUCKET`은 빈 값. 기존 비밀번호·JWT·관리자 설정은 유지한다. 실제 `.env`는 Git에 넣지 않는다.

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
"$(brew --prefix postgresql@18)/bin/psql" -h 127.0.0.1 -U bangjach_local -d bangjach
python -m app.jobs.maintenance
```

DB 도구: 호스트 `127.0.0.1`, 포트 `5432`, 사용자 `bangjach_local`, DB `bangjach`. 비밀번호는 로컬 `.env`의 값.

## 작업 후 GitHub 저장

각 저장소에서 관련 검사 후 변경 파일만 선택한다.

```bash
git add <변경한 파일>
git commit -m 'feat/short summary'
git push origin main
```

오류 수정은 `fix/short summary`. 이제 push는 소스 저장·CI 실행이며 운영 자동 배포는 중지했다.

## 이전 기록·백업

- 카페 67개·테마 100개·사용자·로그인 세션: 모든 테이블 행 수와 UTC 기준 해시 비교 완료.
- 마이그레이션: `c49af128e307`. 테마 사진 100개는 `.uploads/review-photos/themes`에 보관.
- 이전 백업: `../backups/2026-11-05-local-migration/postgres-public.dump`. 실제 데이터·비밀값이 들어 있는 백업과 `.uploads`는 Git에 올리지 않는다.
- 기존 Cloud Run은 외부 접근 중지, Cloud Scheduler는 일시 중지, Cloud Build 자동 배포 트리거는 비활성화.
- Cloud SQL `bangjach-postgresql-dev`는 2026-11-05 사용자 승인 후 삭제 완료. 프로젝트에 Cloud SQL 인스턴스는 없다. 로컬 DB·사진 백업은 보관하며, 기존 사진 버킷·빌드 이미지 저장소는 남아 있어 별도 저장 요금이 발생할 수 있다.
- 과거 Cloud Run·Cloud SQL 배포와 2026-11-04 소형 DB 이전 기록은 Git 이력에 남아 있다.
