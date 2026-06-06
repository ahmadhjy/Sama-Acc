# Sama Tours **Website** — PythonAnywhere deployment (same account as ERP)

Use this document when deploying the **marketing/company website** (Django templates, minimal) on the **same PythonAnywhere account** as the ERP (`Samatours2026`). Goal: reuse infrastructure once, avoid duplicate mistakes, keep apps isolated.

---

## Copy-paste prompt for Cursor / another agent

```
Deploy a second Django project on PythonAnywhere for user Samatours2026.

CONTEXT — ALREADY LIVE (do not break):
- ERP "Sama Accounting" is deployed at https://samatours2026.pythonanywhere.com
- ERP path: /home/Samatours2026/Sama-Acc
- ERP venv: /home/Samatours2026/.virtualenvs/sama-accounting
- ERP Postgres DB: sama_acc, user sama_app (separate from website DB)
- PostgreSQL server: Samatours2026-5298.postgres.pythonanywhere-services.com:15298
- Static mapping pattern: /static/ → project/staticfiles (after collectstatic)

NEW PROJECT — SAMA TOURS WEBSITE:
- Django + Django templates, minimal marketing site (not the ERP)
- GitHub repo: [USER WILL FILL: owner/repo URL]
- Should be a SECOND web app on the same PA account (or custom domain if plan allows)
- Reuse PostgreSQL SERVER but create NEW database + NEW user (e.g. sama_web / sama_website_db)
- Do NOT reuse ERP virtualenv — create new venv: sama-website
- Do NOT reuse ERP WSGI, static mappings, or DB credentials

REQUIREMENTS FOR THE CODEBASE (prepare before deploy):
1. Split settings: config.settings.development + config.settings.production (env vars)
2. requirements.txt pinned
3. STATIC_ROOT + collectstatic; STATIC_URL = '/static/'
4. DEBUG=False in production; ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS from env
5. SECRET_KEY from env only
6. .gitignore: db.sqlite3, .env, staticfiles/, media/
7. deploy/pythonanywhere_wsgi.py.example with placeholders
8. No demo passwords in templates

PYTHONANYWHERE STEPS (website — mirror ERP lessons):
1. Bash: git clone [repo] → ~/Sama-Website (or chosen folder name)
2. mkvirtualenv --python=/usr/bin/python3.10 sama-website
3. pip install -r requirements.txt
4. Databases → Postgres console: CREATE DATABASE sama_website; CREATE USER sama_web WITH PASSWORD '...'; GRANT...
5. Web → Add NEW web app (Manual config, Python 3.10) — second app may need custom domain or PA subdomain if plan allows two apps
6. New app: source code, working directory, virtualenv paths for WEBSITE only
7. WSGI file: DJANGO_SETTINGS_MODULE=config.settings.production + Postgres env for sama_web/sama_website
8. Static files: /static/ → /home/Samatours2026/[WebsiteFolder]/staticfiles
9. migrate, collectstatic, createsuperuser (if needed), Reload
10. Force HTTPS on Web tab if available

AVOID:
- Pointing website static files to ERP staticfiles folder
- Same Postgres database/user as ERP
- Same virtualenv as ERP
- Putting ERP and website in one WSGI file (use two web apps)
- Forgetting collectstatic (causes unstyled pages like ERP had)
- Using GitHub password for git clone (use PAT)

DELIVERABLES:
- Updated production settings + WSGI example in website repo
- Short DEPLOY.md with exact paths for Samatours2026
- Confirm CSS loads: /static/css/... returns 200

User account: Samatours2026
ERP reference file on disk: Sama-Acc/PYTHONANYWHERE_REFERENCE.txt
```

---

## Architecture on one PythonAnywhere account

```
Samatours2026 (account)
├── Web app 1: samatours2026.pythonanywhere.com  →  ERP (Sama-Acc)     ✅ live
├── Web app 2: [new].pythonanywhere.com          →  Website (new repo)  ← to deploy
├── Postgres server (one)
│   ├── Database: sama_acc      / User: sama_app   → ERP only
│   └── Database: sama_website  / User: sama_web    → Website only (create in console)
├── .virtualenvs/sama-accounting  → ERP
└── .virtualenvs/sama-website     → Website (new)
```

---

## What you can reuse vs must duplicate

| Item | Reuse? | Notes |
|------|--------|--------|
| PA account login | Yes | Same dashboard |
| Postgres **server** (host/port) | Yes | Same Address + Port from Databases tab |
| Postgres **database** | **No** | New `CREATE DATABASE` for website |
| Postgres **app user** | **No** | New `CREATE USER` with own password |
| Virtualenv | **No** | `sama-website` separate from `sama-accounting` |
| Web app | **No** | Add second web app (check plan limit) |
| WSGI file | **No** | Each web app has its own WSGI |
| Static files mapping | **No** | Each app maps to its own `staticfiles/` |
| GitHub PAT | Yes | Same token for private repos |
| Deployment checklist | Yes | Same steps, different paths/names |
| Domain brand | Yes | samatours2026.pythonanywhere.com taken by ERP |

---

## Second web app URL options

Paid PythonAnywhere plans often allow **multiple web apps**:

- **Option A:** Second subdomain, e.g. `www-samatours2026.pythonanywhere.com` or PA-assigned name when you click "Add a new web app"
- **Option B:** **Custom domain** on the website app (e.g. `www.samatourslb.com`) while ERP stays on `samatours2026.pythonanywhere.com`
- Check **Web** tab → whether "Add a new web app" is available on your plan

---

## Website Postgres setup (SQL template)

Run in **Databases → Start postgres console** (same server as ERP):

```sql
CREATE DATABASE sama_website;
CREATE USER sama_web WITH PASSWORD 'your-lowercase-app-password';
ALTER ROLE sama_web SET client_encoding TO 'utf8';
ALTER ROLE sama_web SET default_transaction_isolation TO 'read committed';
ALTER ROLE sama_web SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE sama_website TO sama_web;
\c sama_website
GRANT ALL ON SCHEMA public TO sama_web;
```

Use in website WSGI:

- `DJANGO_DB_NAME=sama_website`
- `DJANGO_DB_USER=sama_web`
- Same `DJANGO_DB_HOST` and `DJANGO_DB_PORT` as ERP

---

## Website WSGI template (fill when repo is cloned)

```python
import os
import sys

PROJECT_HOME = "/home/Samatours2026/Sama-Website"  # adjust folder name
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
os.environ["DJANGO_SECRET_KEY"] = "NEW_SECRET_KEY_NOT_ERP_KEY"
os.environ["DJANGO_ALLOWED_HOSTS"] = "YOUR_WEBSITE_HOSTNAME.pythonanywhere.com"
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = "https://YOUR_WEBSITE_HOSTNAME.pythonanywhere.com"
os.environ["DJANGO_DEBUG"] = "False"

os.environ["DJANGO_DB_ENGINE"] = "postgresql"
os.environ["DJANGO_DB_NAME"] = "sama_website"
os.environ["DJANGO_DB_USER"] = "sama_web"
os.environ["DJANGO_DB_PASSWORD"] = "website-db-password"
os.environ["DJANGO_DB_HOST"] = "Samatours2026-5298.postgres.pythonanywhere-services.com"
os.environ["DJANGO_DB_PORT"] = "15298"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

---

## Pre-deploy checklist for the **website** repo (before PA)

- [ ] `requirements.txt` exists
- [ ] `config/settings/production.py` reads env vars
- [ ] `STATIC_ROOT` defined; `collectstatic` documented
- [ ] No hardcoded `SECRET_KEY` or `DEBUG=True` in production
- [ ] `.gitignore` excludes `.env`, `db.sqlite3`, `staticfiles/`
- [ ] `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` documented
- [ ] Repo pushed to GitHub (public or PAT for private)

---

## Deploy order (recommended)

1. Prepare website repo (settings split + deploy docs) — **on PC**
2. Push to GitHub
3. PA: clone website repo (new folder, not inside Sama-Acc)
4. PA: new venv + `pip install`
5. PA: new Postgres DB/user for website
6. PA: **new** web app + WSGI + static mappings
7. PA: `migrate` + `collectstatic` + Reload
8. Test website CSS URL and homepage
9. (Optional) Point custom domain to website web app only

---

## ERP reference

Full ERP paths and env var names: **`PYTHONANYWHERE_REFERENCE.txt`** in the Sama-Acc repo.

---

## When starting the website project in Cursor

Open the **website** repo folder (not Sama-Acc) and say:

> "Deploy this Django site to PythonAnywhere account Samatours2026 as a second web app. ERP is already live at samatours2026.pythonanywhere.com using Sama-Acc. Follow WEBSITE_DEPLOYMENT_PROMPT.md and PYTHONANYWHERE_REFERENCE.txt from the ERP repo for shared Postgres host/port. Create separate DB, user, venv, and static mappings."

Provide your **website GitHub URL** and desired **folder name** on PA (`Sama-Website` or similar).
