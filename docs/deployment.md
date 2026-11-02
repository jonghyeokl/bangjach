# 배포 명령어

기본값 설정 완료: 프로젝트 `bangjach-api`, 리전 `asia-northeast3`. 아래 명령에서는 생략한다.

## 백엔드 코드 변경

변경 사항을 커밋한 뒤 자동 배포에 연결된 브랜치에서 실행한다.

```bash
git push
```

## DB 구조 변경

마이그레이션 파일을 작성·검증한 뒤 적용한다. 기존 서버와 호환되는 변경은 DB 적용 후 push한다. 컬럼 삭제·이름 변경은 적용 순서를 별도 확인한다.

첫 번째 터미널:

```bash
cloud-sql-proxy --port 5433 bangjach-api:asia-northeast3:bangjach-postgresql
```

두 번째 터미널:

```bash
cd /Users/jonghyeok/bangjach/bangjach
source .venv/bin/activate
unset DATABASE_URL
alembic upgrade head
alembic current
```

## 운영 환경변수 변경

```bash
gcloud run services update bangjach-api --update-env-vars '변수명=새값'
```

여러 변수:

```bash
gcloud run services update bangjach-api --update-env-vars '변수1=값1,변수2=값2'
```

변경 시 자동 재배포된다. 로컬 `.env`는 push해도 반영되지 않으며, `JWT_SECRET`은 유지한다.

## 배포 후 확인

```bash
curl -i 'https://bangjach-api-192693215385.asia-northeast3.run.app/cafe/v1'
```

`200` 응답 확인 후 변경한 기능을 테스트한다.

## 앱 실행

```bash
cd /Users/jonghyeok/bangjach/bangjach-app
npx expo start
```

환경변수 변경 후에는 `npx expo start --clear`. 설치 앱 배포는 별도 빌드·업데이트가 필요하다.

## DB 연결 구분

- 로컬 `.env`: `127.0.0.1:5433` → 프록시를 통해 **운영 DB**에 연결.
- Cloud Run: `/cloudsql/bangjach-api:asia-northeast3:bangjach-postgresql` 소켓 사용.
- 테스트는 별도 테스트 DB에서 실행. 운영 DB에서 테스트 데이터 초기화 스크립트를 실행하지 않는다.

## 컬럼 순서

`id → 테이블별 항목 → created_dt → updated_dt`. `rate_limit`은 `key → window → count`.
2026-11-02 초기 마이그레이션을 이 순서로 수정하고, 사용자 요청에 따라 운영 DB를 데이터 없이 재생성했다.
기존 DB에서 `alembic upgrade head`만 다시 실행해도 컬럼 순서가 바뀌지는 않는다.

## 리뷰 사진 기능 최초 적용

1. 위 DB 절차대로 `alembic upgrade head` 실행 (`b7c81d29e104`). 기존 데이터는 유지된다.
2. 사진 저장소 생성·권한 설정 (한 번만):

```bash
gcloud storage buckets create gs://bangjach-api-192693215385-review-photos --location=asia-northeast3 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding gs://bangjach-api-192693215385-review-photos --member=serviceAccount:192693215385-compute@developer.gserviceaccount.com --role=roles/storage.objectUser
```

Cloud Run 서비스 계정을 변경했다면 `--member`에도 변경된 계정을 넣는다. 버킷 이름이 이미 사용 중이면 다른 이름으로 만들고 아래 값도 맞춘다.

3. 코드 커밋·push 후 자동 배포 완료 확인, 환경변수 적용:

```bash
gcloud run services update bangjach-api --update-env-vars 'REVIEW_PHOTO_BUCKET=bangjach-api-192693215385-review-photos'
```

4. 앱 재시작:

```bash
cd /Users/jonghyeok/bangjach/bangjach-app
source ../dev-env.sh
npm ci
npx expo start --clear
```

사진 없는 리뷰·피드도 새 DB 마이그레이션이 필요하다. 운영 저장소 설정 전에는 사진 업로드가 503으로 안내된다. 저장소는 공개하지 않고 API에서 게시된 리뷰 사진만 제공한다.

미저장·삭제된 사진 정리 (24시간 이후, 동일 DB/버킷 설정 환경에서 주기적으로 실행):

```bash
python -m app.jobs.cleanup_photos
```

자동 스케줄은 아직 등록하지 않았다. 로컬에서 운영 사진 정리 시에도 `REVIEW_PHOTO_BUCKET`을 운영 값으로 설정해야 한다.

참고: [버킷 생성](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/create), [버킷 권한 설정](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/add-iam-policy-binding).
