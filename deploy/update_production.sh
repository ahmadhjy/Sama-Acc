#!/usr/bin/env bash
#
# Safe production update for Sama Accounting on PythonAnywhere.
#
# What it does (in order):
#   1. Preflight checks (paths, venv, no concurrent run, clean git tree)
#   2. Database backup (SQLite copy or pg_dump / mysqldump)
#   3. git pull --ff-only (never force, never reset)
#   4. pip install -r requirements.txt
#   5. django check
#   6. migrate --plan (logged) then migrate --noinput
#   7. collectstatic --noinput
#   8. Idempotent seed_destinations (adds missing rows only)
#
# What it NEVER does:
#   - git reset --hard / git clean / force push
#   - makemigrations, flush, loaddata, migrate --fake
#   - Deletes database or media files
#
# Usage (PythonAnywhere Bash console):
#   cd ~/Sama-Acc
#   bash deploy/update_production.sh
#
# First time: copy deploy/update_production.local.conf.example to
# deploy/update_production.local.conf and adjust paths.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONF_FILE="${SCRIPT_DIR}/update_production.local.conf"
LOCK_FILE="${SCRIPT_DIR}/.update.lock"
LOG_DIR="${SCRIPT_DIR}/logs"
BACKUP_DIR="${SCRIPT_DIR}/backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/update_${STAMP}.log"

# Defaults (overridden by local.conf)
SAMA_PROJECT_DIR="${PROJECT_DIR}"
SAMA_VENV_DIR="${HOME}/.virtualenvs/sama-accounting"
SAMA_GIT_BRANCH="main"
DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
SAMA_BACKUP_KEEP=10
SAMA_REQUIRE_BACKUP=1

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$LOG_FILE"
}

die() {
  log "ERROR: $*"
  exit 1
}

cleanup() {
  rm -f "$LOCK_FILE"
}
trap cleanup EXIT

mkdir -p "$LOG_DIR" "$BACKUP_DIR"

if [[ -f "$CONF_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONF_FILE"
  log "Loaded config: $CONF_FILE"
fi

# Optional server-side .env (gitignored) for Bash-only tools like pg_dump
if [[ -f "${SAMA_PROJECT_DIR}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SAMA_PROJECT_DIR}/.env"
  set +a
  log "Loaded environment from ${SAMA_PROJECT_DIR}/.env"
fi

export DJANGO_SETTINGS_MODULE

cd "$SAMA_PROJECT_DIR" || die "Project directory not found: $SAMA_PROJECT_DIR"

if [[ ! -f "manage.py" ]]; then
  die "manage.py not found in $SAMA_PROJECT_DIR — check SAMA_PROJECT_DIR in update_production.local.conf"
fi

if [[ ! -d "$SAMA_VENV_DIR" ]]; then
  die "Virtualenv not found: $SAMA_VENV_DIR"
fi

# shellcheck source=/dev/null
source "${SAMA_VENV_DIR}/bin/activate"

if [[ -e "$LOCK_FILE" ]]; then
  die "Another update appears to be running (lock: $LOCK_FILE). If stale, remove it manually after confirming no update is active."
fi
touch "$LOCK_FILE"

log "========== Sama Accounting production update started =========="
log "Project: $SAMA_PROJECT_DIR"
log "Branch:  $SAMA_GIT_BRANCH"
log "Log:     $LOG_FILE"

# --- Git safety: refuse dirty tree or non-fast-forward without manual fix ---
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "Not a git repository. Clone from GitHub first."
fi

if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  die "Working tree has local changes. Commit, stash, or discard them before updating production."
fi

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "$SAMA_GIT_BRANCH" ]]; then
  die "On branch '$CURRENT_BRANCH' but SAMA_GIT_BRANCH is '$SAMA_GIT_BRANCH'. Switch branch manually first."
fi

# --- Database backup (before any code/schema change) ---
BACKUP_PATH=""
if [[ "$SAMA_REQUIRE_BACKUP" == "1" ]]; then
  log "Creating database backup..."
  if BACKUP_PATH="$(python deploy/backup_database.py 2>>"$LOG_FILE")"; then
    log "Backup saved: $BACKUP_PATH"
    # Rotate old backups
    mapfile -t OLD_BACKUPS < <(ls -1t "$BACKUP_DIR" 2>/dev/null || true)
    if ((${#OLD_BACKUPS[@]} > SAMA_BACKUP_KEEP)); then
      for old in "${OLD_BACKUPS[@]:SAMA_BACKUP_KEEP}"; do
        rm -f "${BACKUP_DIR}/${old}"
        log "Removed old backup: ${BACKUP_DIR}/${old}"
      done
    fi
  else
    die "Database backup failed. Fix backup or set SAMA_REQUIRE_BACKUP=0 in local.conf (not recommended)."
  fi
else
  log "WARNING: Skipping database backup (SAMA_REQUIRE_BACKUP=0)"
fi

# --- Pull latest code (fast-forward only) ---
log "Fetching from origin..."
git fetch origin "$SAMA_GIT_BRANCH"

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/${SAMA_GIT_BRANCH}")"

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  log "Already up to date ($LOCAL_SHA). Continuing with dependency/migration checks."
else
  if git merge-base --is-ancestor "$LOCAL_SHA" "$REMOTE_SHA"; then
    log "Fast-forward pull: $LOCAL_SHA -> $REMOTE_SHA"
    git pull --ff-only origin "$SAMA_GIT_BRANCH" | tee -a "$LOG_FILE"
  else
    die "Cannot fast-forward. Local commits diverge from origin. Resolve manually — never force-pull on production."
  fi
fi

# --- Dependencies ---
log "Installing Python dependencies..."
pip install --upgrade pip >>"$LOG_FILE" 2>&1
pip install -r requirements.txt >>"$LOG_FILE" 2>&1

# --- Django checks ---
log "Running django check..."
python manage.py check >>"$LOG_FILE" 2>&1

PENDING="$(python manage.py showmigrations --plan 2>/dev/null | grep -c '\[ \]' || true)"
if [[ "$PENDING" -gt 0 ]]; then
  log "Pending migrations ($PENDING):"
  python manage.py migrate --plan 2>&1 | tee -a "$LOG_FILE"
else
  log "No pending migrations."
fi

# --- Apply migrations (safe forward-only) ---
log "Applying migrations..."
python manage.py migrate --noinput 2>&1 | tee -a "$LOG_FILE"

# --- Static files ---
log "Collecting static files..."
python manage.py collectstatic --noinput >>"$LOG_FILE" 2>&1

# --- Idempotent data seeds (safe to re-run) ---
if python manage.py help seed_destinations >/dev/null 2>&1; then
  log "Running seed_destinations (idempotent)..."
  python manage.py seed_destinations >>"$LOG_FILE" 2>&1 || log "WARNING: seed_destinations failed (non-fatal)"
fi

log "========== Update finished successfully =========="
log ""
log "NEXT STEP: Open PythonAnywhere Web tab and click Reload for your site."
log "If anything looks wrong, restore from backup: $BACKUP_PATH"
log "Full log: $LOG_FILE"
