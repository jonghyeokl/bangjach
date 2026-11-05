"""Two-level regions; major areas follow the observed bbabang public selector."""

# Append only: positions are persistent subregion IDs. Never reorder existing names.
AREA_NAMES = {
    1: [
        "홍대",
        "강남",
        "건대",
        "대학로",
        "신촌",
        "신림",
        "잠실",
        "신사",
        "노원",
        "수유",
        "명동",
        "성신여대",
        "영등포",
        "종각",
        "목동",
        "용산",
        "구로",
        "연신내",
        "천호",
        "노량진",
        "이수",
        "동대문",
        "서울대입구",
        "선릉",
        "왕십리",
        "성수",
        "마곡",
        "회기",
    ],
    2: [
        "수원",
        "부천",
        "성남",
        "일산",
        "안산",
        "동탄",
        "범계",
        "평택",
        "의정부",
        "안양",
        "화정",
        "구리",
        "화성",
        "김포",
        "산본",
        "광명",
        "동두천",
        "용인",
        "이천",
        "오산",
        "남양주",
        "포천",
    ],
    3: ["부평", "구월", "송도", "인천 기타"],
    4: ["대전", "청주", "천안", "세종", "홍성", "당진"],
    5: ["춘천", "원주", "강릉", "동해"],
    6: ["부산", "대구", "울산", "포항", "양산", "진주", "창원", "구미", "경주", "김해", "안동"],
    7: ["광주", "전주", "여수", "익산", "순천", "목포", "군산"],
    8: ["제주"],
}

SUBREGIONS = {
    region * 100 + i: (region, name)
    for region, names in AREA_NAMES.items()
    for i, name in enumerate(names, 1)
}


def validate_subregion(region, subregion):
    if subregion is not None and (
        subregion not in SUBREGIONS or SUBREGIONS[subregion][0] != region
    ):
        raise ValueError("상위 지역에 맞는 세부 지역을 선택하세요.")
    return subregion
