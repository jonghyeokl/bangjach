# 배포 명령어

기본값: 프로젝트 `bangjach-api`, 리전 `asia-northeast3`.

## 적용된 설정 (2026-11-04)

- 운영 API: https://bangjach-api-192693215385.asia-northeast3.run.app
- DB: `bangjach-postgresql-dev` — PostgreSQL 18, Enterprise `db-g1-small`, 단일 존, SSD 10GB(자동 증가 상한 20GB). 매일 백업 7개 보관.
- 마이그레이션: `c49af128e307`. 기존 카페 67개·테마 100개·사용자·로그인 세션 이전 및 데이터 해시 검증.
- Cloud Run: 최소 0개, 서비스 전체 최대 2개 인스턴스. API·정기 작업 모두 새 DB 사용.
- 사진: 비공개 버킷 `bangjach-api-192693215385-review-photos`, Cloud Run 접근 권한·환경변수 설정.
- 정기 작업: `bangjach-maintenance`. `bangjach-daily-maintenance` 예약으로 매일 **한국 시간 04:00**에 통계 갱신·24시간 지난 미사용 사진 정리.
- 정기 작업은 빌드팩 런처(`/cnb/lifecycle/launcher`)로 `python -m app.jobs.maintenance` 실행. 실제 실행 성공 확인.
- `main` push → `cloudbuild.yaml` → API 자동 배포 + 정기 작업 이미지 갱신.
- 백엔드·앱은 별도 저장소. 앱 push는 소스 저장이며 App Store 배포는 아니다.

- 기존 `bangjach-postgresql`과 MySQL `bangjach`은 중지 상태로 보존. 저장공간 비용은 삭제 전까지 남는다.
- 이전 백업: `../backups/2026-11-04-db-migration/postgres-public.dump` (PostgreSQL 18 클라이언트로 복원). Git에 추가하지 않는다.

## 코드 변경

관련 검사 후 각 저장소에서 실행한다. 작업 중인 비밀값이나 무관한 파일은 추가하지 않는다.

```bash
git add <변경한 파일>
git commit -m 'feat/short summary'
git push origin main
```

오류 수정 커밋은 `fix/short summary`. 제목은 짧은 영어로 작성한다. 작업 후 commit·push는 기본 작업 규칙이다.

## DB 구조 변경

기존 서버와 호환되는 변경은 마이그레이션을 먼저 적용한 뒤 push한다. 삭제·이름 변경은 적용 순서를 따로 검토한다.

첫 번째 터미널:

```bash
cloud-sql-proxy --port 5433 bangjach-api:asia-northeast3:bangjach-postgresql-dev
```

두 번째 터미널:

```bash
cd /Users/jonghyeok/bangjach/bangjach
source .venv/bin/activate
unset DATABASE_URL
alembic upgrade head
alembic current
```

로컬 `.env`의 `127.0.0.1:5433`은 프록시를 통한 운영 DB 연결이다. 테스트 데이터 초기화에는 사용하지 않는다.
Cloud Run은 `/cloudsql/bangjach-api:asia-northeast3:bangjach-postgresql-dev` 소켓을 사용한다.

## 운영 환경변수 변경

```bash
gcloud run services update bangjach-api --update-env-vars '변수명=새값'
```

DB·사진 버킷 등 정기 작업도 사용하는 값을 바꿨다면 함께 적용한다.

```bash
gcloud run jobs update bangjach-maintenance --update-env-vars '변수명=새값'
```

로컬 `.env`는 push해도 운영에 반영되지 않는다. 기존 `JWT_SECRET`은 유지한다.

## 배포·정기 작업 확인

```bash
curl -i 'https://bangjach-api-192693215385.asia-northeast3.run.app/cafe/v1'
gcloud builds list --region=global --limit=3
gcloud run jobs executions list --job=bangjach-maintenance
```

수동 정기 작업 실행:

```bash
gcloud scheduler jobs run bangjach-daily-maintenance --location=asia-northeast3
```

## 앱 실행

```bash
cd /Users/jonghyeok/bangjach/bangjach-app
source ../dev-env.sh
npx expo start --clear
```

휴대폰과 컴퓨터를 같은 Wi-Fi에 연결하고 Expo Go에서 QR 코드를 연다. 설치 앱·스토어 배포는 별도 빌드가 필요하다.

## 참고

컬럼 순서: `id → 테이블별 항목 → created_dt → updated_dt`. `rate_limit`은 `key → window → count`.
2026-11-02 사용자의 데이터 삭제 허용에 따라 기존 DB를 이 순서로 재생성했다. 이번 사진 테이블 추가는 기존 데이터를 삭제하지 않았다.

사진 선택/업로드 실기기 확인과 실제 LLM 공급자 설정은 별도다. 사진·정기 작업 설정은 완료했으며 최초 생성 명령을 다시 실행할 필요 없다.

[Cloud Run 정기 실행 안내](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)
