# 실제 DB·사진

- `bangjach.db`: 백엔드가 직접 읽고 수정하는 SQLite DB. 별도 복원 없이 사용한다.
- `photos/`: 테마·리뷰 사진. 백엔드의 `/media/v1/...` 경로로 제공한다.
- 기존 카페·테마뿐 아니라 사용자·비밀번호 해시·세션 등 전체 테이블을 포함한다(사용자 요청). 공개 저장소에서는 이 데이터도 내려받을 수 있다.
- `.env`의 JWT 서명 키·LLM API 키는 포함하지 않는다. 관리자 권한은 `.env`의 `ADMIN_USER_IDS`로 설정한다.

## GitHub에 변경 반영

서버·배치·DB 도구를 종료한 뒤 백엔드 폴더에서 실행한다. 실행 중 생기는 journal/WAL 파일은 Git에서 제외한다.

```bash
sqlite3 data/bangjach.db "PRAGMA integrity_check;"
git add data/bangjach.db data/photos
git commit -m 'feat/update database'
git push origin main
```

별도 export/import는 필요 없다. DB 파일의 동시 변경은 자동 병합할 수 없으므로 다른 버전으로 바꾸기 전에 현재 파일을 백업한다. GitHub는 실행 중인 DB의 변경을 자동 동기화하지 않는다.
