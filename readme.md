# 방자취 API

방탈출 카페와 테마를 탐색하고 리뷰·친구·캘린더로 플레이 경험을 기록하는 FastAPI 백엔드. **카페는 방탈출 카페이며 한 카페가 여러 테마를 운영한다(1:N).**

기준 명세: [1차 구현 계획](https://www.notion.so/40b605e41f1d8081836dc070bbcb830c). 앱은 별도 [bangjach-app 저장소](https://github.com/jonghyeokl/bangjach-app)에 있다.

## 구현 범위

- 전화번호·비밀번호 가입/로그인, 중복 불가 닉네임, Argon2id 해시, JWT와 서버 세션, 리프레시 회전/로그아웃.
- 관리자 카페·테마 등록, 카페/테마 검색, 지역·장르·점수 필터와 정렬, 홈페이지 링크.
- 사용자·테마당 리뷰 하나. **평점과 플레이 날짜 필수**, 점수는 1~5의 0.5 간격. 나머지는 선택 입력.
- 고정 키워드의 LLM 분류, any/all 키워드 및 인원 리뷰 필터, 키워드별 개수.
- 닉네임 친구 요청·수락·거절·취소·해제, 나와 일행이 안 한 테마 검색.
- 월별 캘린더, 캘린더/일행 검색 공개 설정(기본 친구만). 리뷰와 리뷰 날짜는 항상 공개.
- 사용자별 평점 보정과 일별 통계 작업. 보정 강도 10, 항목별 최소 3명. 원점수 보존.

실제 LLM 호출은 공급자·모델·키 설정이 필요하다. 미설정/분석 실패 시 리뷰를 저장하고 FAILED 상태를 반환한다. 본문 없으면 SKIPPED다. 시간표·예약·추천·비밀번호 재설정·휴대폰 인증은 이번 범위에 없다.

## 설치와 실행

Python 3.14.3 기준, 고정 의존성은 requirements.txt. 기존 .env를 복사 명령으로 덮어쓰지 않는다.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 최초 복제 시에만
cp .env.example .env
# DATABASE_URL이 의도한 로컬 DB인지 먼저 확인
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

[Swagger 문서](http://localhost:8000/docs), [상태 확인](http://localhost:8000/api/v1/health). 기능 API는 `/user/v1`, `/theme/v1`, `/review/v1`, `/friend/v1`, `/friend-request/v1`, `/cafe/v1`, `/meta/v1/enums`다. health만 기존 `/api/v1/health`를 유지한다. 요청/응답 타입과 검증 규칙은 Swagger에서 볼 수 있다.

## 환경변수

| 변수 | 용도 |
| --- | --- |
| DATABASE_URL | 로컬 SQLite 또는 `postgresql+asyncpg://...`. 운영은 PostgreSQL 필수 |
| ENVIRONMENT | production이면 PostgreSQL과 최소 32자 JWT_SECRET 검증 |
| JWT_SECRET | 토큰 서명 비밀값. 개발에서 비우면 재시작 때 로그인이 만료됨 |
| CORS_ORIGINS | 웹 출처의 JSON 배열, 기본 localhost/127.0.0.1:8081 |
| ADMIN_USER_IDS | 관리자 사용자 UUID의 JSON 배열. 기본 [] |
| ACCESS_TOKEN_MINUTES / REFRESH_TOKEN_DAYS | 기본 15분 / 30일 |
| LLM_BASE_URL / LLM_MODEL / LLM_API_KEY | JSON 응답을 지원하는 chat/completions 호환 공급자 |
| LLM_TIMEOUT_SECONDS | 기본 10초, 실패해도 리뷰 저장 |
| RATE_LIMIT_ENABLED | 기본 true, DB를 공유하는 인스턴스 간 호출 제한 |

실제 비밀값은 Git에 넣지 않는다. 운영은 Secret Manager로 연결한다. EXPO_PUBLIC 변수에 비밀값을 넣으면 안 된다. 모바일 실기기는 PC와 같은 네트워크에서 PC의 LAN IP를 API 주소로 사용한다.

## 초기 데이터 입력

1. 정상 가입/로그인하고 `GET /user/v1/me`에서 UUID 확인.
2. 해당 UUID를 서버의 `ADMIN_USER_IDS=["UUID"]`에 넣고 서버 재시작.
3. Swagger의 Authorize에 액세스 토큰을 입력한 뒤 `POST /cafe/v1`, `POST /theme/v1` 순서로 등록.

카페/테마 이름은 지점·동명 테마 때문에 고유값으로 제한하지 않는다. 이미지는 URL로 입력한다. 공식 장르와 초기 점수는 입력하지 않으며 리뷰에서 집계한다.

## 통계 작업

```bash
python -m app.jobs.statistics
```

전체 리뷰의 같은 스냅샷으로 사용자 편향과 테마 통계를 갱신한다. 리뷰 수정/삭제 후 통계는 다음 작업에 반영된다. 운영은 Cloud Run Job과 Scheduler로 매일 04:00 Asia/Seoul 실행하도록 설정한다. 이 저장소 변경만으로 외부 예약이 생성되지는 않는다.

## 검증

```bash
pytest -q
ruff check .
ruff format --check .
python -m pip check
```

기본 테스트는 임시 SQLite를 쓰며 `.env`의 운영 DB를 사용하지 않는다. PostgreSQL 검증은 **삭제 가능한 로컬 테스트 DB**를 준비한 뒤 실행한다. 테스트는 테이블 데이터를 비운다. 접속 사용자는 bangjach_test, 호스트는 localhost/127.0.0.1만 허용한다.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://bangjach_test@127.0.0.1:55432/postgres pytest -q
```

PostgreSQL에서는 배열 제약조건·동시 리뷰/친구 요청·토큰 회전을 추가 검증한다. GitHub Actions도 PostgreSQL 17에서 마이그레이션, 검사, 테스트를 실행한다. 로컬에서 SQLite 9개 통과/PG 전용 1개 제외, PostgreSQL 10개 통과를 확인했다. 테스트 수는 여러 시나리오를 묶은 함수 기준이다.

앱 브라우저 테스트용 데이터 준비: 로컬 테스트 DB를 DATABASE_URL로 지정하여 `python -m tests.seed_e2e` 실행 후 API 시작. 이 스크립트는 테스트 DB를 비우고 가상 테마와 계정을 넣는다. 실제 초기 데이터 입력용이 아니다.

## 구조와 문서

- app/domain: 모델, Enum, 입력·출력 스키마
- app/api: 기능별 HTTP API
- app/services: 접근권한, 키워드 분석, 조회 직렬화, 호출 제한
- app/core: 설정·DB·인증·오류
- app/jobs/statistics.py: 일별 통계 작업
- migrations: 초기 스키마, PostgreSQL 배열/표현식 인덱스·제약조건
- [구현 결정과 요구사항 대응](docs/implementation.md)
- [운영 적용·배포 절차](docs/deployment.md)

현재 검증은 로컬 코드·DB·앱 대상이다. 운영 DB 마이그레이션, Cloud Run 재배포, GitHub 트리거 변경, Scheduler 설정, 실제 LLM 호출은 별도 적용이 필요하다. Dockerfile을 추가했으며 컨테이너 이미지를 실제 빌드/배포한 것은 아니다. 기존 Procfile도 유지한다.
