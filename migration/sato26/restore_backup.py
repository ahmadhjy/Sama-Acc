"""Restore SATO26 .bak to SQL Server and print date audit (Python, no sqlcmd required)."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pyodbc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP = PROJECT_ROOT.parent / "Full Backup" / "SATO26_backup_2026_06_25_150935_2847034.bak"
ARCHIVE_DIR = PROJECT_ROOT / "exports" / "sato26" / "backup"
DB_NAME = "SATO26_RESTORE"


def pick_driver() -> str:
    drivers = pyodbc.drivers()
    for name in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ):
        if name in drivers:
            return name
    raise RuntimeError(f"No SQL Server ODBC driver found. Have: {drivers}")


def connect(server: str, database: str = "master"):
    driver = pick_driver()
    extra = "TrustServerCertificate=yes;Encrypt=yes;" if "18" in driver or "17" in driver else ""
    return pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"Trusted_Connection=yes;{extra}",
        autocommit=True,
    )


def restore(server: str, backup_path: Path, data_dir: Path):
    data_mdf = data_dir / f"{DB_NAME}.mdf"
    log_ldf = data_dir / f"{DB_NAME}_log.ldf"
    sql = f"""
    RESTORE DATABASE [{DB_NAME}]
    FROM DISK = N'{backup_path}'
    WITH
      MOVE N'SATO26' TO N'{data_mdf}',
      MOVE N'SATO26_log' TO N'{log_ldf}',
      REPLACE,
      STATS = 10;
    """
    with connect(server) as conn:
        conn.cursor().execute(sql)


def audit(server: str):
    with connect(server, DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT MIN(Date), MAX(Date), COUNT(1) FROM dbo.SalesHeader WHERE Type='SI'")
        si = cur.fetchone()
        cur.execute("SELECT MIN(Date), MAX(Date), COUNT(1) FROM dbo.JournalHeader")
        jh = cur.fetchone()
        print(f"Sales invoices (SI): {si[2]} rows, {si[0]} to {si[1]}")
        print(f"Journals:          {jh[2]} rows, {jh[0]} to {jh[1]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--server", default="localhost")
    parser.add_argument("--skip-restore", action="store_true")
    args = parser.parse_args()

    backup = args.backup.resolve()
    if not backup.exists():
        raise SystemExit(f"Backup not found: {backup}")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_copy = ARCHIVE_DIR / backup.name
    shutil.copy2(backup, archive_copy)
    print(f"Archived backup to {archive_copy}")
    restore_path = archive_copy

    data_dir = PROJECT_ROOT / "exports" / "sato26"
    data_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_restore:
        print(f"Restoring {restore_path.name} to {DB_NAME} on {args.server} ...")
        restore(args.server, restore_path, data_dir)
        print("Restore complete.")

    print("\n=== Date audit ===")
    audit(args.server)


if __name__ == "__main__":
    main()
