# 방자취 API

방탈출 카페와 테마를 탐색하고 리뷰·팔로우·캘린더로 플레이 경험을 기록하는 FastAPI 백엔드. **카페는 방탈출 카페이며 한 카페가 여러 테마를 운영한다(1:N).**

기준 명세: [1차 구현 계획](https://www.notion.so/40b605e41f1d8081836dc070bbcb830c). 앱은 별도 [bangjach-app 저장소](https://github.com/jonghyeokl/bangjach-app)에 있다.

## 구현 범위

- 전화번호·비밀번호 가입/로그인, 중복 불가 닉네임, Argon2id 해시, JWT와 서버 세션, 리프레시 회전/로그아웃.
- 관리자 카페·테마 등록, 카페/테마 검색, 지역→세부 지역·장르·점수 필터와 정렬, 홈페이지 링크.
- 사용자·테마당 리뷰 하나. **평점과 플레이 날짜 필수**, 점수는 1~5의 0.5 간격. 나머지는 선택 입력.
- OpenAI Responses API로 10개 리뷰 주제의 언급 여부 분석. 이머시브·분리·직원연출 포함, 모두 미해당 가능.
- 닉네임 검색·팔로우·승인·거절·취소, 최근 30일 팔로잉/전체 피드·최신순/좋아요 순·리뷰 좋아요, 타인 프로필/캘린더/목록. 일행은 검색을 허용한 승인된 팔로잉만.
- 기본 비공개 계정: 승인된 팔로워에게 리뷰·사진·캘린더·팔로우 목록 공개. 공개 전환 시 대기 요청도 승인.
- 사용자별 평점 보정과 일별 통계 작업. 보정 강도 10, 항목별 최소 3명. 원점수 보존.

실제 AI 호출은 `.env`의 `OPENAI_API_KEY` 설정이 필요하다. 기본 모델은 `gpt-4.1-mini`. 미설정/분석 실패 시 리뷰를 저장하고 FAILED 상태를 반환한다. 본문 없으면 SKIPPED다. 시간표·예약·추천·비밀번호 재설정·휴대폰 인증은 이번 범위에 없다.

## 설치와 실행

현재는 **SQLite + 로컬 사진 저장소**로 실행한다. 백엔드가 repo 안의 `data/bangjach.db`를 직접 읽고 수정한다. GitHub에도 같은 DB 파일과 `data/photos`를 저장하므로, 복제 후 별도 DB 설치·시작·데이터 복원이 필요 없다. [일상 실행 명령어](docs/deployment.md).

백엔드 폴더에서 최초 준비:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 기존 .env가 있으면 복사하지 않는다.
cp -n .env.example .env
unset DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Python 3.14 기준. DB 경로와 사진 경로는 실행 위치와 무관하게 백엔드 repo 기준으로 해석한다. 기존 로컬 `.env`의 JWT·관리자 설정은 유지한다. 새 환경에서 로그인 유지가 필요하면 `.env`의 `JWT_SECRET`에 고정된 임의 값을 설정한다.

[DB 파일과 Git 관리](data/README.md). DB에는 요청한 전체 데이터(계정·비밀번호 해시·세션 포함)를 보존했다. `.env`의 JWT 서명 키·LLM API 키는 올리지 않는다.

[Swagger 문서](http://localhost:8000/docs), [상태 확인](http://localhost:8000/api/v1/health). 기능 API는 `/user/v1`, `/theme/v1`, `/review/v1`, `/follow/v1`, `/feed/v1`, `/cafe/v1`, `/meta/v1/enums`다. health만 기존 `/api/v1/health`를 유지한다. 요청/응답 타입과 검증 규칙은 Swagger에서 볼 수 있다.

## 환경변수

| 변수 | 용도 |
| --- | --- |
| DATABASE_URL | `sqlite+aiosqlite:///./data/bangjach.db` |
| ENVIRONMENT | production이면 PostgreSQL과 최소 32자 JWT_SECRET 검증 |
| JWT_SECRET | 토큰 서명 비밀값. 개발에서 비우면 재시작 때 로그인이 만료됨 |
| CORS_ORIGINS | 웹 출처의 JSON 배열, 기본 localhost/127.0.0.1:8081 |
| ADMIN_USER_IDS | 관리자 사용자 UUID의 JSON 배열. 기본 [] |
| ACCESS_TOKEN_MINUTES / REFRESH_TOKEN_DAYS | 기본 15분 / 30일 |
| OPENAI_API_KEY / OPENAI_MODEL | OpenAI API 키 / 기본 gpt-4.1-mini |
| LLM_TIMEOUT_SECONDS | 기본 10초, 실패해도 리뷰 저장 |
| RATE_LIMIT_ENABLED | 기본 true, DB를 공유하는 인스턴스 간 호출 제한 |

환경변수의 실제 비밀값은 Git에 넣지 않는다. EXPO_PUBLIC 변수에 비밀값을 넣으면 안 된다. 모바일 실기기는 PC와 같은 네트워크에서 PC의 LAN IP를 API 주소로 사용한다.

## 초기 데이터 입력

1. 정상 가입/로그인하고 `GET /user/v1/me`에서 UUID 확인.
2. 해당 UUID를 서버의 `ADMIN_USER_IDS=["UUID"]`에 넣고 서버 재시작.
3. Swagger의 Authorize에 액세스 토큰을 입력한 뒤 `POST /cafe/v1`, `POST /theme/v1` 순서로 등록.

카페/테마 이름은 지점·동명 테마 때문에 고유값으로 제한하지 않는다. 앱에서 이미지를 직접 업로드한다. 공식 장르와 초기 점수는 입력하지 않으며 리뷰에서 집계한다.

## 통계 작업

```bash
python scripts/refresh_statistics.py
```

이 Mac의 다른 Codex 채팅에서도 **“통계 갱신해줘”**로 실행할 수 있다. [스킬 원본](codex-skills/bangjach-statistics/SKILL.md).

전체 리뷰의 같은 스냅샷으로 사용자 편향과 테마 통계를 갱신한다. 리뷰 수정/삭제 후 통계는 다음 작업에 반영된다. 로컬에서는 필요할 때 수동 실행한다. 기존 Cloud Scheduler 예약은 로컬 전환 후 삭제했다.

## 검증

```bash
pytest -q
ruff check .
ruff format --check .
python -m pip check
```

기본 테스트는 별도 임시 SQLite를 쓰며 `data/bangjach.db`를 변경하지 않는다. PostgreSQL 검증은 **삭제 가능한 로컬 테스트 DB**를 준비한 뒤 실행한다. 테스트는 테이블 데이터를 비운다. 접속 사용자는 bangjach_test, 호스트는 localhost/127.0.0.1만 허용한다.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://bangjach_test@127.0.0.1:55432/postgres pytest -q
```

SQLite에서도 외래키·리뷰 코드 제약조건과 UTC 시간을 보존한다. 로컬 SQLite 트랜잭션은 `BEGIN IMMEDIATE`로 직렬화해 동시 토큰 갱신·친구 요청·사진 연결을 보호한다. 쓰기 대기는 최대 30초이며, 다중 사용자 운영 환경을 위한 설정은 아니다. GitHub Actions는 SQLite와 PostgreSQL 양쪽에서 마이그레이션·스키마 검사·테스트를 실행한다.

앱 브라우저 테스트용 DB는 실제 파일과 분리한다. 백엔드 폴더의 별도 터미널에서:

```bash
export DATABASE_URL="sqlite+aiosqlite:///$(python -c 'import tempfile; print(tempfile.gettempdir())')/bangjach-e2e.db"
alembic upgrade head
python -m tests.seed_e2e
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

이 시드 명령은 지정된 임시 DB만 비우고 가상 계정·테마를 넣는다. 테스트 종료 후 `unset DATABASE_URL`로 실제 DB 설정을 다시 사용한다.

## 구조와 문서

- app/domain: 모델, Enum, 입력·출력 스키마
- app/api: 기능별 HTTP API
- app/services: 접근권한, 키워드 분석, 조회 직렬화, 호출 제한
- app/core: 설정·DB·인증·오류
- app/jobs/statistics.py: 일별 통계 작업
- migrations: 초기 스키마, PostgreSQL 배열/표현식 인덱스·제약조건
- [구현 결정과 요구사항 대응](docs/implementation.md)
- [운영 적용·배포 절차](docs/deployment.md)

Cloud Run 배포 및 실제 API 검증 이력이 있으며, 현재는 로컬 실행으로 전환했다. Dockerfile·Procfile·cloudbuild.yaml은 재배포 시 사용할 수 있도록 남겨둔다. Cloud Run 서비스·정기 작업·자동 배포 트리거·클라우드 저장소는 삭제했으며 재배포 시 다시 구성해야 한다.


## 피드·좋아요·리뷰 사진

- `GET /feed/v1?scope=following&sort=newest&page=1&page_size=20`: 로그인 필요. 기본은 승인된 팔로잉·최신순. `scope=all`은 공개 계정 + 승인된 팔로잉. 모든 경우 작성일 기준 최근 30일만 조회한다.
- `sort=likes`: 좋아요 수 내림차순, 동률이면 작성일·ID 내림차순. 수정으로 순서를 올리지 않는다.
- `PUT /review/v1/{id}/like`, `DELETE /review/v1/{id}/like`: 좋아요/취소. 로그인 및 리뷰 조회 권한 필요, 사용자당 한 번만 집계. 응답은 `review_id`, `like_count`, `is_liked`. 리뷰 조회 응답에도 `like_count`, `is_liked` 포함.
- 리뷰 응답: `theme_image_url`, `photos: [{id, url}]` 포함. 사진 URL은 API 기준 상대 경로.
- `POST /media/v1/review-photos`: 로그인 후 이미지 파일 바이트 전송 (`application/octet-stream`). `{id, url}` 반환. 이 단계에서는 공개되지 않는다.
- 리뷰 작성/수정 JSON에 `photo_ids: [uuid, ...]` (최대 5개). 본인의 미사용 사진 또는 해당 리뷰의 기존 사진만 허용. 수정 시 생략하면 유지, `[]`는 모두 제거.
- 사진: JPEG/PNG/WebP, 최대 8MB·2,500만 화소. 긴 변 1600px 이하 JPEG로 변환하며 EXIF 제거. 리뷰 삭제·사진 제거 즉시 공개 접근 차단.
- 운영: 비공개 Google Cloud Storage, 로컬: `data/photos`. [배포·운영 명령](docs/deployment.md).
- 미저장·분리된 사진은 `python -m app.jobs.cleanup_photos`로 24시간 이후 정리. 현재는 `python -m app.jobs.maintenance`로 수동 실행.


## 과거 운영 적용 (2026-11-02, 현재 운영 중지)

사진 테이블 마이그레이션과 비공개 Cloud Storage 연결을 적용했다. 운영 API에서 임시 계정의 로그인·친구 피드 조회·사진 업로드·로그아웃을 검증하고 계정/사진을 정리했다.
`cloudbuild.yaml`은 main push 시 API와 정기 작업 이미지를 함께 갱신한다. 정기 작업은 매일 한국 시간 04:00에 통계 갱신과 미사용 사진 정리를 실행한다. 변경 후 commit·push와 짧은 영어 커밋 제목 규칙은 `AGENTS.md`에 기록했다.

관리자 UI 연동: 가입·로그인·토큰 갱신·`GET /user/v1/me` 응답의 `is_admin`은 서버의 `ADMIN_USER_IDS`에서 계산한다. 앱은 이를 사용해 관리자 탭을 표시하며 카페·테마 등록 권한은 각 POST API에서도 다시 검사한다. DB 변경은 필요 없다.

테마 사진 등록: 관리자 전용 `POST /theme/v1/with-photo`에 multipart 형식으로 `data`(기존 테마 등록 JSON 문자열)와 `photo`(파일 1장)를 보낸다. 사진 없는 등록은 기존 `POST /theme/v1`을 사용한다. 사진은 기존 비공개 버킷의 `themes/` 경로에 저장하며, 응답 `image_url`은 API 기준 상대 경로다. JPEG/PNG/WebP·8MB·2,500만 화소 제한, EXIF 제거·1600px 축소를 적용한다. 저장 실패 시 테마는 생성하지 않는다. DB 마이그레이션·추가 환경변수는 필요 없다.

일행 검색: `/user/v1/search?purpose=party&q=...`는 수락된 친구이면서 일행 검색을 허용한 사용자만 반환한다. `/theme/v1`의 `party_user_id`에도 같은 제한을 적용한다. 친구 추가용 검색(`purpose=friend`)은 유지한다.

## 빠방 테스트 데이터 일괄 등록

앱 저장소의 수집기로 카페 지역·주소·전화번호가 포함된 JSON과 사진을 준비한 뒤 실행한다. DB 연결은 `.env`의 `DATABASE_URL`을 사용한다.

```sh
# 검증/미리보기만 (DB·버킷에 쓰지 않음)
.venv/bin/python -m app.jobs.import_bbabang /수집폴더/themes.json

# 실제 등록 (repo 안의 SQLite DB·사진 폴더에 저장)
.venv/bin/python -m app.jobs.import_bbabang /수집폴더/themes.json --apply --local-photos
```

- 앱의 `npm run collect:bbabang -- --input <JSON> --import-db --apply --local-photos`으로 다운로드·CSV·DB 등록을 한 번에 실행할 수 있다.
- 원본 ID 기반 UUID로 중복을 방지하고 기존 카페/테마는 이름도 대조한다. 기존 내용을 덮어쓰지 않는다. 카페명 중복·주소 불일치·필수 정보 누락은 보고하고 중단한다.
- SQLite 트랜잭션으로 임포터 실행을 직렬화한다. DB 쓰기는 한 트랜잭션으로 처리하며 실패하면 이번에 저장한 사진도 정리한다. 기존 데이터 삭제나 새 마이그레이션은 없다.
- 가져온 포스터는 최대 6,400만 화소·12MB를 허용하고 1600px JPEG로 축소한다. 일반 업로드 API의 제한은 그대로다.
- 원본 추천 점수·리뷰 수는 저장하지 않는다. 방자취 통계는 실제 사용자 리뷰로 계산한다.
- 현재 환경에서는 `--local-photos`를 지정한다.
