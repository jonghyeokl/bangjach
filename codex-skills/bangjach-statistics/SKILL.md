---
name: bangjach-statistics
description: Refresh Bangjach theme statistics in the local SQLite database on this Mac. Use when the user says "통계 갱신해줘", "방자취 통계 갱신", or requests Bangjach rating/genre statistics recalculation, including in another Codex chat.
---

# 방자취 통계 갱신

대상 저장소: `/Users/jonghyeok/bangjach/bangjach`.

1. 저장소의 `AGENTS.md`와 `git status --short`를 확인한다. 기존 변경을 덮어쓰지 않는다.
2. 아래 명령을 실행한다. `.env` 내용이나 인증정보는 출력하지 않는다.

```sh
cd /Users/jonghyeok/bangjach/bangjach
.venv/bin/python scripts/refresh_statistics.py
```

3. 명령의 종료 코드, 갱신 테마 수와 최종 검증 결과를 확인한다. 실패하면 완료라고 말하지 않는다. DB 경로 불일치·마이그레이션 불일치 시 임의로 다른 DB에 실행하거나 테이블을 생성하지 않는다.
4. 요청받은 것은 전체 통계 재계산이다. 리뷰 키워드 AI 재분석, 데이터 수집, 클라우드 배포는 실행하지 않는다.
5. 저장소 규칙에 따라 이번 변경만 commit/push한다. 기존에 `data/bangjach.db`가 수정되어 있었다면 통계 변경만 분리해 커밋할 수 없으므로 DB 파일은 임의로 포함하지 말고 그 사실을 알린다. 커밋 제목은 `feat/refresh statistics`. Git 작업이 실패해도 통계 갱신 성공 여부와 구분해 알린다.
6. 한국어로 갱신 테마 수, 검증 성공, commit/push 여부를 간결하게 보고한다.
