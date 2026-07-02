# Restore the full SATO26 backup from "Full Backup" folder and export CSV inventory.
#
# Usage (PowerShell):
#   cd "C:\Users\ME\Desktop\Acc System\Sama Accounting\scripts"
#   .\restore_full_backup.ps1
#
param(
    [string]$BackupPath = "$PSScriptRoot\..\..\Full Backup\SATO26_backup_2026_06_25_150935_2847034.bak",
    [string]$SqlInstance = "localhost",
    [string]$DatabaseName = "SATO26_RESTORE",
    [string]$ExportDir = "$PSScriptRoot\..\exports\sato26"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupPath)) {
    Write-Error "Backup not found: $BackupPath"
}

$backupDir = Join-Path $ExportDir "backup"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$archiveName = Split-Path $BackupPath -Leaf
$archiveCopy = Join-Path $backupDir $archiveName
Copy-Item -Path $BackupPath -Destination $archiveCopy -Force
Write-Host "==> Archived backup copy to $archiveCopy"

New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
$inventoryDir = Join-Path $ExportDir "inventory"
New-Item -ItemType Directory -Force -Path $inventoryDir | Out-Null

Write-Host "==> Reading backup file list..."
$fileList = sqlcmd -S $SqlInstance -Q "RESTORE FILELISTONLY FROM DISK = N'$BackupPath'" -W -s "|"
$fileList | Out-File (Join-Path $inventoryDir "filelistonly.txt")

$DataLogical = "SATO26"
$LogLogical = "SATO26_log"
$dataFile = Join-Path $ExportDir "$DatabaseName.mdf"
$logFile = Join-Path $ExportDir "${DatabaseName}_log.ldf"

Write-Host "==> Restoring database $DatabaseName on $SqlInstance ..."
$restoreSql = @"
RESTORE DATABASE [$DatabaseName]
FROM DISK = N'$BackupPath'
WITH
  MOVE N'$DataLogical' TO N'$dataFile',
  MOVE N'$LogLogical' TO N'$logFile',
  REPLACE,
  STATS = 10;
"@
sqlcmd -S $SqlInstance -Q $restoreSql

Write-Host "==> Date audit (sales + journals)..."
sqlcmd -S $SqlInstance -d $DatabaseName -Q @"
SELECT 'SI' AS kind, MIN(Date) AS min_date, MAX(Date) AS max_date, COUNT(1) AS row_count
FROM dbo.SalesHeader WHERE Type='SI'
UNION ALL
SELECT 'Journals', MIN(Date), MAX(Date), COUNT(1) FROM dbo.JournalHeader;
"@ -W

Write-Host "==> Table row counts..."
$rowCountSql = @"
USE [$DatabaseName];
SET NOCOUNT ON;
SELECT s.name AS schema_name, t.name AS table_name, p.rows AS row_count
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0,1)
ORDER BY p.rows DESC;
"@
sqlcmd -S $SqlInstance -Q $rowCountSql -W -s "," -o (Join-Path $inventoryDir "tables_rowcounts.csv")

$exports = @{
    "SalesHeader"    = "SELECT * FROM dbo.SalesHeader"
    "SalesFooter"    = "SELECT * FROM dbo.SalesFooter"
    "IDCard"         = "SELECT * FROM dbo.IDCard"
    "Accounts"       = "SELECT * FROM dbo.Accounts"
    "JournalHeader"  = "SELECT * FROM dbo.JournalHeader"
    "JournalDetail"  = "SELECT * FROM dbo.JournalDetail"
    "Company"        = "SELECT TOP 1 * FROM dbo.Company"
}

foreach ($name in $exports.Keys) {
    $out = Join-Path $ExportDir "$name.csv"
    Write-Host "==> Exporting $name ..."
    sqlcmd -S $SqlInstance -d $DatabaseName -Q $exports[$name] -W -s "," -o $out
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  python manage.py import_sato26"
