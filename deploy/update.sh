#!/usr/bin/env bash
#
# Sama Accounting (ERP) — production update (PythonAnywhere)
#
# One-time setup:
#   cd ~/Sama-Acc
#   cp deploy/production.env.example deploy/production.env
#   nano deploy/production.env   # paste values from your ERP WSGI file
#   chmod +x deploy/update.sh
#
# Every update after you push to GitHub:
#   cd ~/Sama-Acc && ./deploy/update.sh
#
set -euo pipefail

PROJECT_DIR="/home/Samatours2026/Sama-Acc"
VENV_DIR="/home/Samatours2026/.virtualenvs/sama-accounting"
ENV_FILE="${PROJECT_DIR}/deploy/production.env"
GIT_BRANCH="${GIT_BRANCH:-main}"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

if [[ ! -d "$PROJECT_DIR" ]]; then
  die "Project folder not found: $PROJECT_DIR"
fi

cd "$PROJECT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  die "Missing $ENV_FILE — run: cp deploy/production.env.example deploy/production.env && nano deploy/production.env"
fi

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  die "Virtualenv not found: $VENV_DIR"
fi

# Server should match GitHub. Drop local edits to tracked files (uploads in media/ are not affected).
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  log "Resetting local edits to tracked files (uploads in media/ are not affected)"
  git reset --hard HEAD
fi

load_env_file() {
  local file="$1"
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//$'\r'/}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      if [[ "$val" =~ ^\'(.*)\'$ ]]; then
        val="${BASH_REMATCH[1]}"
      elif [[ "$val" =~ ^\"(.*)\"$ ]]; then
        val="${BASH_REMATCH[1]}"
      fi
      export "$key=$val"
    fi
  done < "$file"
}

log "Loading production environment"
load_env_file "$ENV_FILE"
export DJANGO_SETTINGS_MODULE=config.settings.production

if [[ "$DJANGO_SECRET_KEY" == replace-with-your-secret-key* ]]; then
  die "Edit deploy/production.env — set DJANGO_SECRET_KEY from your ERP WSGI file"
fi
if [[ "$DJANGO_DB_PASSWORD" == replace-with-db-password* ]]; then
  die "Edit deploy/production.env — set DJANGO_DB_PASSWORD from your ERP WSGI file"
fi

log "Activating virtualenv: sama-accounting"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Pulling latest code from GitHub (branch: $GIT_BRANCH)"
git fetch origin "$GIT_BRANCH"
git pull --ff-only origin "$GIT_BRANCH"

log "Installing Python dependencies"
pip install -r requirements.txt --disable-pip-version-check -q

log "Checking database connection"
python manage.py check --database default

PENDING="$(python manage.py showmigrations --plan 2>/dev/null | grep -c '\[ \]' || true)"
if [[ "$PENDING" -gt 0 ]]; then
  log "Applying $PENDING pending migration(s) (existing data is preserved)"
  python manage.py migrate --noinput
else
  log "No pending migrations"
fi

log "Collecting static files"
python manage.py collectstatic --noinput

# Idempotent — adds missing destination rows only; safe to run every deploy.
if python manage.py help seed_destinations >/dev/null 2>&1; then
  log "Seeding destinations (idempotent)"
  python manage.py seed_destinations
fi

log "Rebuilding payment allocations (oldest due-date FIFO)"
python manage.py rebuild_payment_allocations

if [[ -n "${PA_WSGI_FILE:-}" && -f "$PA_WSGI_FILE" ]]; then
  log "Reloading web app via WSGI touch"
  touch "$PA_WSGI_FILE"
else
  log "Reload manually: Web tab → ERP app (samatours2026.pythonanywhere.com) → Reload"
  log "Do NOT reload the SAMA-TOURS website app — that is a separate project."
fi

log "Done. ERP: https://${DJANGO_ALLOWED_HOSTS%%,*}/"
