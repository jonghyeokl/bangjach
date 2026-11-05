"""Populate missing cafe subregions from explicit names/address terms; never overwrite."""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.domain.models import Cafe  # noqa: E402
from app.domain.regions import SUBREGIONS  # noqa: E402

# Narrow, reviewed address aliases for the imported cafes. Unmatched cafes stay null.
ALIASES = {
    1: [
        ("마곡", ["마곡"]),
        ("회기", ["휘경로"]),
        ("성수", ["성수"]),
        ("신사", ["가로수길", "도산대로13길"]),
        ("홍대", ["홍대", "서교동", "와우산로", "양화로 176", "독막로", "홍익로", "잔다리로"]),
        ("신촌", ["창천동", "연세로"]),
        ("건대", ["건대", "아차산로", "화양동", "자양동 13"]),
        ("잠실", ["잠실", "삼전동", "백제고분로7길"]),
        ("강남", ["강남", "역삼동", "테헤란로", "봉은사로2길", "서초대로77길", "반포동 734"]),
    ],
    2: [("범계", ["호계동 1044", "평촌대로217번길"]), ("동탄", ["동탄"])],
    3: [("부평", ["부평"]), ("구월", ["남동구 성말로"]), ("송도", ["송도"])],
}


def infer(region, name, address):
    text = name + " " + address
    for label, terms in ALIASES.get(region, []):
        if any(term in text for term in terms):
            return next(code for code, value in SUBREGIONS.items() if value == (region, label))
    candidates = [
        (code, label)
        for code, (parent, label) in SUBREGIONS.items()
        if parent == region
        and (
            label in name
            or re.search(r"(?:^|\s)" + re.escape(label) + r"(?:광역시|특별시|시)?(?=\s|$)", address)
        )
    ]
    return candidates[0][0] if len(candidates) == 1 else None


async def main():
    async with SessionLocal() as db:
        rows = (await db.scalars(select(Cafe).where(Cafe.subregion.is_(None)))).all()
        changed = 0
        for row in rows:
            code = infer(row.region, row.name, row.address)
            if code is not None:
                row.subregion = code
                changed += 1
        await db.commit()
        print(f"Assigned {changed} cafe subregions; {len(rows) - changed} unmatched (left null)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
