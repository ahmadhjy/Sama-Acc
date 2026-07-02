"""Payment gap analysis: which legacy RV/PV were not imported."""
import os, sys
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import django
django.setup()

import pyodbc
from treasury.models import Payment

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=SATO26_RESTORE;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;Encrypt=yes;"
)
cur = conn.cursor()

def rv_client_amount(jvno):
    cur.execute(
        """
        SELECT d.ACCNO, d.AMT, d.DC, d.Note
        FROM JournalDetail d WHERE d.Type='RV' AND d.JVNO=?
        """,
        jvno,
    )
    rows = cur.fetchall()
    client_row = next((r for r in rows if str(r[0] or "").startswith("411") and str(r[2]).upper() == "C"), None)
    if not client_row:
        client_row = next((r for r in rows if str(r[0] or "").startswith("411")), None)
    return rows, client_row

def pv_supplier_amount(jvno):
    cur.execute(
        """
        SELECT d.ACCNO, d.AMT, d.DC, d.Note
        FROM JournalDetail d WHERE d.Type='PV' AND d.JVNO=?
        """,
        jvno,
    )
    rows = cur.fetchall()
    sup_row = next((r for r in rows if str(r[0] or "").startswith("401") and str(r[2]).upper() == "D"), None)
    if not sup_row:
        sup_row = next((r for r in rows if str(r[0] or "").startswith("401")), None)
    return rows, sup_row

print("=== MISSING RV (legacy 62, imported 60) ===")
cur.execute("SELECT JVNO, Date, Note FROM JournalHeader WHERE Type='RV' ORDER BY CAST(JVNO AS INT)")
missing_rv = []
for jvno, dt, note in cur.fetchall():
    receipt = f"SATO26-RV-{str(jvno).zfill(5)}"
    if not Payment.objects.filter(receipt_no=receipt).exists():
        rows, cr = rv_client_amount(str(jvno))
        missing_rv.append((jvno, dt, note, cr, rows))
        print(f"\nJVNO {jvno} date={dt} note={note!r}")
        print(f"  client line: {cr}")
        if not cr:
            for r in rows:
                print(f"    {r}")

print(f"\nTotal missing RV: {len(missing_rv)}")

print("\n=== MISSING PV (legacy 58, imported 41) ===")
cur.execute("SELECT JVNO, Date, Note FROM JournalHeader WHERE Type='PV' ORDER BY CAST(JVNO AS INT)")
missing_pv = []
for jvno, dt, note in cur.fetchall():
    receipt = f"SATO26-PV-{str(jvno).zfill(5)}"
    if not Payment.objects.filter(receipt_no=receipt).exists():
        rows, sr = pv_supplier_amount(str(jvno))
        missing_pv.append((jvno, dt, note, sr, rows))
        print(f"\nJVNO {jvno} date={dt} note={note!r}")
        print(f"  supplier line: {sr}")
        if not sr:
            for r in rows[:6]:
                print(f"    {r}")

print(f"\nTotal missing PV: {len(missing_pv)}")

print("\n=== OP opening balance journal ===")
cur.execute("SELECT * FROM JournalHeader WHERE Type='OP'")
cols = [d[0] for d in cur.description]
for row in cur.fetchall():
    print(dict(zip(cols, row)))
cur.execute("SELECT * FROM JournalDetail WHERE Type='OP'")
cols = [d[0] for d in cur.description]
for row in cur.fetchall():
    print(dict(zip(cols, row)))

print("\n=== Legacy SalesHeader AmountPaid (all zero?) ===")
cur.execute("SELECT COUNT(*) FROM SalesHeader WHERE Type='SI' AND CAST(AmountPaid AS DECIMAL(18,2)) <> 0")
print("Invoices with AmountPaid != 0:", cur.fetchone()[0])

print("\n=== Staging payments count ===")
staging = Path(__file__).resolve().parents[2] / "exports" / "sato26" / "staging" / "payments.jsonl"
print("payments.jsonl lines:", sum(1 for _ in staging.open(encoding="utf-8")))

conn.close()
