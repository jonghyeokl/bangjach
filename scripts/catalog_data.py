"""Export/restore public cafe/theme data; never export account or session tables."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog"
PHOTOS = ROOT / ".uploads/review-photos"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    url = make_url(os.environ.get("DATABASE_URL") or config["DATABASE_URL"])
    if url.host not in {"localhost", "127.0.0.1"} or not url.drivername.startswith("postgresql"):
        raise SystemExit("Only a local PostgreSQL database is allowed")
    pg = os.environ.get("PG_BIN")
    if not pg:
        pg = str(
            Path(subprocess.check_output(["brew", "--prefix", "postgresql@18"], text=True).strip())
            / "bin"
        )
    env = os.environ.copy()
    env.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "",
    )

    def sql(query):
        return subprocess.check_output(
            [str(Path(pg) / "psql"), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", query],
            env=env,
            text=True,
        ).strip()

    if args.action == "export":
        # An explicit table allowlist prevents future private tables entering the export.
        with tempfile.TemporaryDirectory(prefix="bangjach-catalog-") as temporary:
            staging = Path(temporary)
            subprocess.run(
                [
                    str(Path(pg) / "pg_dump"),
                    "--data-only",
                    "--no-owner",
                    "--no-acl",
                    "--table=public.cafe",
                    "--table=public.theme",
                    "--file=" + str(staging / "catalog.sql"),
                ],
                env=env,
                check=True,
            )
            dump = staging / "catalog.sql"
            dump.write_text(dump.read_text().rstrip() + "\n")
            themes = json.loads(
                sql("SELECT coalesce(json_agg(t), '[]') FROM (SELECT id, image_url FROM theme) t")
            )
            for theme in themes:
                if theme["image_url"] != f"/media/v1/theme-photos/{theme['id']}":
                    continue
                relative = Path("themes") / f"{theme['id']}.jpg"
                destination = staging / "photos" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(PHOTOS / relative, destination)
            manifest = {
                "tables": ["cafe", "theme"],
                "cafe_count": int(sql("SELECT count(*) FROM cafe")),
                "theme_count": len(themes),
                "sha256": {
                    str(p.relative_to(staging)): digest(p)
                    for p in sorted(staging.rglob("*"))
                    if p.is_file()
                },
            }
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            CATALOG.mkdir(parents=True, exist_ok=True)
            # Only replace generated files, leaving the dataset README intact.
            if (CATALOG / "photos").exists():
                shutil.rmtree(CATALOG / "photos")
            shutil.copytree(staging, CATALOG, dirs_exist_ok=True)
            print(f"Exported {manifest['cafe_count']} cafes / {len(themes)} themes")
    else:
        manifest = json.loads((CATALOG / "manifest.json").read_text())
        if sql("SELECT (SELECT count(*) FROM cafe) + (SELECT count(*) FROM theme)") != "0":
            raise SystemExit(
                "Import requires empty cafe/theme tables; existing data was not changed"
            )
        for name, expected in manifest["sha256"].items():
            source = (CATALOG / name).resolve()
            if not source.is_relative_to(CATALOG.resolve()) or digest(source) != expected:
                raise SystemExit(f"Invalid catalog file: {name}")
        for source in (CATALOG / "photos").rglob("*.jpg"):
            destination = PHOTOS / source.relative_to(CATALOG / "photos")
            if destination.exists() and digest(source) != digest(destination):
                raise SystemExit("An existing local photo differs; import cancelled")
        shutil.copytree(CATALOG / "photos", PHOTOS, dirs_exist_ok=True)
        subprocess.run(
            [
                str(Path(pg) / "psql"),
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "--single-transaction",
                "--file=" + str(CATALOG / "catalog.sql"),
            ],
            env=env,
            check=True,
        )
        print("Catalog restored. User accounts and sessions are not included.")


if __name__ == "__main__":
    main()
