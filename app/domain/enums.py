from enum import IntEnum


class Publicity(IntEnum):
    PRIVATE = 1
    FRIEND_ONLY = 2
    PUBLIC = 3


class Genre(IntEnum):
    HORROR = 1
    EMOTIONAL = 2
    THRILLER = 3
    MYSTERY = 4
    INFILTRATION = 5
    HISTORICAL = 6
    SCIFI = 7
    PUZZLE = 8
    ARCADE = 9
    FANTASY = 10
    COMEDY = 11
    ADVENTURE = 12
    ROMANCE = 13


class Region(IntEnum):
    SEOUL = 1
    GYEONGGI = 2
    INCHEON = 3
    CHUNGCHEONG = 4
    GANGWON = 5
    GYEONGSANG = 6
    JEOLLA = 7
    JEJU = 8


class ReviewKeyword(IntEnum):
    INTERIOR = 1
    EFFECTS = 2
    PUZZLE = 3
    STORY = 4
    ERROR = 5
    GUIDE = 6
    RECOMMEND_SIZE = 7


class KeywordAnalysisStatus(IntEnum):
    SKIPPED = 1
    COMPLETED = 2
    FAILED = 3


LABELS = {
    "publicity": (Publicity, ["비공개", "친구만", "전체"]),
    "genre": (
        Genre,
        [
            "공포",
            "감성",
            "스릴러",
            "추리",
            "잠입",
            "역사",
            "SF",
            "문제방",
            "아케이드",
            "판타지",
            "코믹",
            "모험",
            "로맨스",
        ],
    ),
    "region": (Region, ["서울", "경기", "인천", "충청", "강원", "경상", "전라", "제주"]),
    "review_keyword": (
        ReviewKeyword,
        ["인테리어", "연출", "문제", "스토리", "장치오류", "가이드", "추천인원"],
    ),
    "keyword_analysis_status": (KeywordAnalysisStatus, ["본문 없음", "분석 완료", "분석 실패"]),
}
