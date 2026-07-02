import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=SATO26_RESTORE;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;Encrypt=yes;"
)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM SalesHeader WHERE Type='SI' AND Date > '2026-01-31'")
print("SI after Jan 2026:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM JournalHeader WHERE Date > '2026-01-31'")
print("Journals after Jan 2026:", cur.fetchone()[0])

cur.execute("SELECT ACCNO, DC, AMT FROM JournalDetail WHERE Type='OP' AND ACCNO LIKE '411%'")
op411 = cur.fetchall()
print("OP client (411) lines:", len(op411))
net = 0
for acc, dc, amt in op411:
    v = float(amt)
    net += v if dc == "D" else -v
    print(f"  {acc} {dc} {amt}")
print("OP 411 net (positive = client owes):", net)

cur.execute(
    "SELECT SUM(CAST(d.AMT AS DECIMAL(18,2))) FROM JournalDetail d "
    "WHERE d.Type='RV' AND d.DC='C' AND d.ACCNO LIKE '411%'"
)
print("Legacy RV client credits total:", cur.fetchone()[0])

cur.execute("SELECT SUM(CAST(GrossTotal AS DECIMAL(18,2))) FROM SalesHeader WHERE Type='SI'")
si = float(cur.fetchone()[0] or 0)
rv = float(cur.execute(
    "SELECT SUM(CAST(d.AMT AS DECIMAL(18,2))) FROM JournalDetail d "
    "WHERE d.Type='RV' AND d.DC='C' AND d.ACCNO LIKE '411%'"
).fetchone()[0] or 0)
print(f"Legacy implied AR (SI - RV client receipts): {si - rv}")

conn.close()
