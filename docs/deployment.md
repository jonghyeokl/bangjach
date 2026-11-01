# 운영 적용 순서

현재 저장소는 실행 가능한 코드와 마이그레이션을 포함한다. 이 문서의 명령은 준비된 절차이며 실제 실행 완료를 뜻하지 않는다. 서비스와 DB의 기존 설정·데이터를 확인하고 적용한다.

1. PostgreSQL 백업 후 운영 DATABASE_URL을 사용하는 별도 마이그레이션 작업에서 `alembic upgrade head`를 실행한다. 웹 서버 시작마다 실행하지 않는다. 이번 초기 마이그레이션은 도메인 테이블 9개와 호출 제한 테이블 1개를 추가한다.
2. Cloud Run에 ENVIRONMENT=production, DATABASE_URL, 최소 32자의 JWT_SECRET, CORS_ORIGINS를 설정한다. DATABASE_URL/JWT_SECRET/LLM_API_KEY는 Secret Manager 연동을 권장한다. 로컬 .env는 배포에 포함되지 않는다.
3. 관리자 계정을 정상 가입하고 `/user/v1/me`의 UUID를 ADMIN_USER_IDS JSON 배열에 추가한다. 휴대폰번호나 닉네임으로 관리자 권한을 부여하지 않는다.
4. 소스 또는 컨테이너로 `bangjach-api`를 배포한다. Dockerfile은 Python 3.14와 PORT를 사용한다. 기존 Buildpacks 방식은 Procfile을 동일하게 유지한다. Dockerfile이 있는 소스 배포는 Dockerfile을 사용하므로 자동 빌드 트리거의 빌드 유형도 확인한다.
5. `/api/v1/health`, `/docs`와 로그인·리뷰 API를 점검한다. health는 DB 연결 점검이 아니다.
6. 같은 이미지·DB 설정을 사용하는 Cloud Run Job을 만들고 실행 명령을 `python`, 인자를 `-m,app.jobs.statistics`로 설정한다. 새벽 04:00 Asia/Seoul을 초기 실행 시각으로 사용한다. Cloud Scheduler가 인증하여 Job을 실행하게 하고 호출 계정에 해당 Job 실행 권한만 부여한다.
7. LLM_BASE_URL(예: 공급자 API의 /v1까지), LLM_MODEL, LLM_API_KEY를 설정한다. `/chat/completions`, JSON response_format을 지원하는지 확인하고 짧은 리뷰로 COMPLETED와 빈 배열·실패 경로를 점검한다.
8. 앱 EXPO_PUBLIC_API_URL을 Cloud Run 서비스의 루트 URL로 설정하고 앱을 다시 빌드한다. 클라이언트 공개 변수에 DB/LLM 비밀 키를 넣지 않는다.

## GitHub 연결

두 저장소에 CI 검사 워크플로가 있다. 기존 Cloud Run의 GitHub 자동 빌드 트리거는 외부 설정이므로 코드를 추가했다고 자동으로 변경되지 않는다. 첫 운영 적용에서는 마이그레이션 후 서비스 배포 순서를 지켜야 한다. 이후 스키마 변경도 마이그레이션 검증을 거쳐 적용한다.

## 로컬과 운영 분리

검증용 PostgreSQL은 localhost의 별도 포트/DB를 사용한다. tests/seed_e2e.py는 로컬 bangjach_test 사용자 접속만 허용하며 해당 테스트 DB 데이터를 지운다. 운영 DB에서는 실행하지 않는다. 실제 데이터는 관리자 POST /cafe/v1, POST /theme/v1으로 입력한다.
