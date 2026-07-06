"""Audit payment gaps: legacy journals vs staging export."""
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "exports" / "sato26" / "staging" / "payments.jsonl"

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=SATO26_RESTORE;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;Encrypt=yes;"
)
cur = conn.cursor()

cur.execute("SELECT Type, COUNT(1) FROM JournalHeader GROUP BY Type ORDER BY Type")
print("=== JournalHeader by type ===")
jh_types = cur.fetchall()
for t, c in jh_types:
    print(f"  {t}: {c}")

cur.execute("SELECT COUNT(1) FROM JournalHeader WHERE Type='RV'")
rv_total = cur.fetchone()[0]
cur.execute("SELECT COUNT(1) FROM JournalHeader WHERE Type='PV'")
pv_total = cur.fetchone()[0]

staging = [json.loads(l) for l in STAGING.read_text(encoding="utf-8").splitlines() if l.strip()]
st_rv = sum(1 for p in staging if p.get("legacy_type") == "RV")
st_pv = sum(1 for p in staging if p.get("legacy_type") == "PV")
print(f"\n=== Totals ===")
print(f"Legacy RV headers: {rv_total}")
print(f"Legacy PV headers: {pv_total}")
print(f"Staging payments:  {len(staging)} (RV {st_rv}, PV {st_pv})")
print(f"Not exported:      RV {rv_total - st_rv}, PV {pv_total - st_pv}")

# Classify skipped RV/PV
def lines_for(typ, jvno):
    cur.execute(
        "SELECT ACCNO, DC, AMT, Note FROM JournalDetail WHERE Type=? AND JVNO=?",
        typ,
        str(jvno),
    )
    return cur.fetchall()


def classify_rv(jvno):
    rows = lines_for("RV", jvno)
    client_c = next((r for r in rows if str(r[0] or "").startswith("411") and str(r[1]).upper() == "C"), None)
    if client_c:
        return "client_receipt"
    if any(str(r[0] or "").startswith("411") for r in rows):
        return "rv_411_other_dc"
    if any(str(r[0] or "").startswith("401") for r in rows):
        return "rv_supplier_related"
    return "rv_other"


def classify_pv(jvno):
    rows = lines_for("PV", jvno)
    sup_d = next((r for r in rows if str(r[0] or "").startswith("401") and str(r[1]).upper() == "D"), None)
    if sup_d:
        return "supplier_payment"
    if any(str(r[0] or "").startswith("626") for r in rows):
        return "expense_626"
    if any(str(r[0] or "").startswith("631") for r in rows):
        return "expense_631"
    if any(str(r[0] or "").startswith("411") for r in rows):
        return "client_refund_411"
    return "pv_other"


staging_jvnos = {(p["legacy_type"], p["legacy_jvno"]) for p in staging}

for typ, classify in (("RV", classify_rv), ("PV", classify_pv)):
    cur.execute(f"SELECT JVNO FROM JournalHeader WHERE Type='{typ}' ORDER BY CAST(JVNO AS INT)")
    skipped_reasons = Counter()
    skipped_samples = defaultdict(list)
    for (jvno,) in cur.fetchall():
        key = (typ, str(jvno))
        if key in staging_jvnos:
            continue
        reason = classify(jvno)
        skipped_reasons[reason] += 1
        if len(skipped_samples[reason]) < 3:
            skipped_samples[reason].append(jvno)
    print(f"\n=== Skipped {typ} ({sum(skipped_reasons.values())}) by reason ===")
    for reason, cnt in skipped_reasons.most_common():
        print(f"  {reason}: {cnt}  (e.g. JVNO {skipped_samples[reason]})")

conn.close()
