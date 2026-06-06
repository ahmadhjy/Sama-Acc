#!/usr/bin/env python
"""
Read-only database backup using Django settings.
Called by deploy/update_production.sh — never modifies or deletes data.
"""
from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    import django

    django.setup()
    from django.conf import settings

    db = settings.DATABASES["default"]
    engine = db["ENGINE"]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project_root / "deploy" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if "sqlite" in engine:
        src = Path(db["NAME"])
        if not src.is_file():
            print(f"ERROR: SQLite database not found: {src}", file=sys.stderr)
            return 1
        dst = backup_dir / f"db_sqlite_{stamp}.sqlite3"
        shutil.copy2(src, dst)
        print(str(dst))
        return 0

    if "postgresql" in engine:
        host = db.get("HOST") or "localhost"
        port = str(db.get("PORT") or "5432")
        name = db["NAME"]
        user = db["USER"]
        password = db.get("PASSWORD") or ""
        dst = backup_dir / f"db_postgresql_{name}_{stamp}.sql"
        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password
        cmd = [
            "pg_dump",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            name,
            "-F",
            "p",
            "-f",
            str(dst),
        ]
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        except FileNotFoundError:
            print("ERROR: pg_dump not found. Install PostgreSQL client tools or back up via PA dashboard.", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: pg_dump failed: {exc.stderr or exc}", file=sys.stderr)
            return 1
        print(str(dst))
        return 0

    if "mysql" in engine:
        host = db.get("HOST") or "localhost"
        port = str(db.get("PORT") or "3306")
        name = db["NAME"]
        user = db["USER"]
        password = db.get("PASSWORD") or ""
        dst = backup_dir / f"db_mysql_{stamp}.sql"
        cmd = [
            "mysqldump",
            "-h",
            host,
            "-P",
            port,
            "-u",
            user,
            f"--result-file={dst}",
            name,
        ]
        env = os.environ.copy()
        if password:
            env["MYSQL_PWD"] = password
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        except FileNotFoundError:
            print("ERROR: mysqldump not found.", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: mysqldump failed: {exc.stderr or exc}", file=sys.stderr)
            return 1
        print(str(dst))
        return 0

    print(f"ERROR: Unsupported database engine: {engine}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
