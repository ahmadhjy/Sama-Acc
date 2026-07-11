"""Restore legacy .bak to SQL Server and print date audit (Python, no sqlcmd required)."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pyodbc

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FULL_BACKUP_DIR = PROJECT_ROOT.parent / "Full Backup"
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


def latest_backup(folder: Path) -> Path:
    for search_dir in (folder, ARCHIVE_DIR, PROJECT_ROOT / "exports" / "sato26" / "backup"):
        if not search_dir.exists():
            continue
        files = sorted(search_dir.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return files[0]
    raise FileNotFoundError(f"No .bak files in {folder}, {ARCHIVE_DIR}, or exports/sato26/backup")


def backup_filelist(server: str, backup_path: Path) -> list[tuple[str, str]]:
    with connect(server) as conn:
        cur = conn.cursor()
        cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{backup_path}'")
        rows = cur.fetchall()
    logical = []
    for row in rows:
        logical_name = row[0]
        file_type = row[2]  # D=data, L=log
        logical.append((logical_name, file_type))
    return logical


def sql_server_paths(server: str) -> tuple[str, str]:
    with connect(server) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(260)), "
            "CAST(SERVERPROPERTY('InstanceDefaultLogPath') AS nvarchar(260))"
        )
        data_path, log_path = cur.fetchone()
    return data_path or "", log_path or data_path or ""


def restore(server: str, backup_path: Path):
    logical = backup_filelist(server, backup_path)
    data_logical = next(name for name, kind in logical if kind == "D")
    log_logical = next(name for name, kind in logical if kind == "L")
    data_dir, log_dir = sql_server_paths(server)
    data_mdf = str(Path(data_dir) / f"{DB_NAME}.mdf")
    log_ldf = str(Path(log_dir) / f"{DB_NAME}_log.ldf")
    sql = f"""
    RESTORE DATABASE [{DB_NAME}]
    FROM DISK = N'{backup_path}'
    WITH
      MOVE N'{data_logical}' TO N'{data_mdf}',
      MOVE N'{log_logical}' TO N'{log_ldf}',
      REPLACE,
      STATS = 5;
    """
    with connect(server) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        while True:
            try:
                cur.fetchall()
            except pyodbc.ProgrammingError:
                pass
            if not cur.nextset():
                break


def audit(server: str):
    with connect(server, DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT MIN(Date), MAX(Date), COUNT(1) FROM dbo.SalesHeader WHERE Type='SI'")
        si = cur.fetchone()
        cur.execute("SELECT MIN(Date), MAX(Date), COUNT(1) FROM dbo.JournalHeader")
        jh = cur.fetchone()
        cur.execute("SELECT COUNT(1) FROM dbo.IDCard")
        clients = cur.fetchone()[0]
        print(f"Clients (IDCard):  {clients}")
        print(f"Sales invoices (SI): {si[2]} rows, {si[0]} to {si[1]}")
        print(f"Journals:          {jh[2]} rows, {jh[0]} to {jh[1]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, default=None, help="Path to .bak (default: newest in Full Backup)")
    parser.add_argument("--server", default="localhost")
    parser.add_argument("--skip-restore", action="store_true")
    args = parser.parse_args()

    source = (args.backup or latest_backup(FULL_BACKUP_DIR)).resolve()
    if not source.exists():
        raise SystemExit(f"Backup not found: {source}")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_copy = ARCHIVE_DIR / source.name
    shutil.copy2(source, archive_copy)
    print(f"Source:   {source}")
    print(f"Archived: {archive_copy}")

    if not args.skip_restore:
        print(f"Restoring to {DB_NAME} on {args.server} ...")
        restore(args.server, archive_copy)
        print("Restore complete.")

    print("\n=== Date audit ===")
    audit(args.server)


if __name__ == "__main__":
    main()
