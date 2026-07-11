#!/usr/bin/env bash
#
# Full production reset: pull latest code, wipe business data, import SATO26 staging.
#
# Usage (PythonAnywhere Bash):
#   cd ~/Sama-Acc
#   chmod +x deploy/full_reimport.sh deploy/update.sh deploy/wipe_for_import.sh deploy/import_sato26.sh
#   bash deploy/full_reimport.sh
#
set -euo pipefail

PROJECT_DIR="/home/Samatours2026/Sama-Acc"
VENV_DIR="/home/Samatours2026/.virtualenvs/sama-accounting"
ENV_FILE="${PROJECT_DIR}/deploy/production.env"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

cd "$PROJECT_DIR" || die "Project folder not found: $PROJECT_DIR"
[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE"
[[ -f "$VENV_DIR/bin/activate" ]] || die "Virtualenv not found: $VENV_DIR"

log "Updating application"
bash deploy/update.sh

log "Wiping all business data"
bash deploy/wipe_for_import.sh --execute

log "Importing SATO26 staging (invoices, payments, operating expenses)"
bash deploy/import_sato26.sh

log "Rebuilding payment allocations (oldest due-date FIFO)"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
set -a && source "$ENV_FILE" && set +a
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py rebuild_payment_allocations

log "Validating supplier trial balance vs legacy PDF"
python migration/sato26/verify_supplier_tb.py

log "Validating import counts and sample client balances"
python manage.py shell -c "
from decimal import Decimal
from accounts_core.models import Client
from reporting.balances import client_ar_balance
from reporting.client_statement_rows import build_client_statement_rows
from sales.models import SalesInvoice
from treasury.models import Payment
from datetime import date

today = date.today()
clients_with_rows = 0
non_zero_balance = 0
for client in Client.objects.all()[:200]:
    rows = build_client_statement_rows(client)
    if not rows:
        continue
    clients_with_rows += 1
    dr = sum((r['debit'] for r in rows), Decimal('0.00'))
    cr = sum((r['credit'] for r in rows), Decimal('0.00'))
    if dr - cr != Decimal('0.00'):
        non_zero_balance += 1

print({
    'invoices': SalesInvoice.objects.count(),
    'payments': Payment.objects.count(),
    'clients_with_statement_rows': clients_with_rows,
    'clients_with_non_zero_balance': non_zero_balance,
    'sample_ar_balance': str(client_ar_balance(Client.objects.first(), today) if Client.objects.exists() else 0),
})
"

log "Done. Reload ERP app from Web tab, then verify client statements and overdue list."
