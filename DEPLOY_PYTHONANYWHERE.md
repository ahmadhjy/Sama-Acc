# Go live on PythonAnywhere — Sama Accounting

Complete step-by-step guide. Do each phase in order. Replace `YOUR_USERNAME` with your PythonAnywhere username everywhere.

---

## Before you start (on your PC)

### 1. Push the project to GitHub

From the `Sama Accounting` folder:

```bash
git init
git add .
git commit -m "Prepare Sama Accounting for PythonAnywhere production"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USER/YOUR_REPO.git
git push -u origin main
```

**Do not commit:** `.env`, `db.sqlite3`, `staticfiles/`, or uploaded files in `media/` (they are in `.gitignore`).

### 2. Generate a secret key (save it somewhere safe)

On your PC:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the output — you will paste it into the PythonAnywhere WSGI file.

---

## Phase 1 — PythonAnywhere account & web app

### Step 1.1 — Log in

1. Go to [https://www.pythonanywhere.com](https://www.pythonanywhere.com)
2. Log in with the account where you already paid for a plan.

### Step 1.2 — Open a Bash console

1. Top menu → **Consoles** → **Bash**

### Step 1.3 — Clone the project

```bash
cd ~
git clone https://github.com/YOUR_GITHUB_USER/YOUR_REPO.git Sama-Accounting
cd Sama-Accounting
```

If the repo root is not the folder with `manage.py`, `cd` into the correct subfolder (e.g. `cd Sama-Accounting/Sama\ Accounting`).

### Step 1.4 — Create a virtual environment and install dependencies

```bash
mkvirtualenv --python=/usr/bin/python3.10 sama-accounting
# If mkvirtualenv fails, use:
# python3.10 -m venv ~/.virtualenvs/sama-accounting
# source ~/.virtualenvs/sama-accounting/bin/activate

workon sama-accounting
pip install --upgrade pip
pip install -r requirements.txt
```

**MySQL (recommended on paid plans):** after creating the database (Phase 2), also run:

```bash
pip install mysqlclient
```

If `mysqlclient` fails to build, use SQLite first (already configured in the WSGI example) and switch to MySQL later.

---

## Phase 2 — Database

Choose **one** option.

### Option A — SQLite (fastest to go live)

No extra setup. The database file will be created at:

`/home/YOUR_USERNAME/Sama-Accounting/db.sqlite3`

Skip to **Phase 3**.

### Option B — MySQL (recommended for production)

1. PythonAnywhere → **Databases** tab
2. Set a **MySQL password** (save it)
3. Click **Initialize MySQL**
4. Note your database name: `YOUR_USERNAME$sama` (create it if needed — name must start with `YOUR_USERNAME$`)
5. Note the host: `YOUR_USERNAME.mysql.pythonanywhere-services.com`

You will use these values in the WSGI file and when running migrations.

---

## Phase 3 — Configure the web app

### Step 3.1 — Create the web app (if not already created)

1. **Web** tab → **Add a new web app**
2. **Manual configuration** (not Django wizard — we already have the project)
3. Python **3.10**

### Step 3.2 — Virtual environment

On the **Web** tab, set:

**Virtualenv:** `/home/YOUR_USERNAME/.virtualenvs/sama-accounting`

(or the path you used in Step 1.4)

### Step 3.3 — WSGI file

1. **Web** tab → link **WSGI configuration file**
2. Delete all default content
3. Copy from `deploy/pythonanywhere_wsgi.py.example` in the repo
4. Replace every placeholder:

| Placeholder | Example |
|-------------|---------|
| `YOUR_USERNAME` | `johndoe` |
| `YOUR_LONG_RANDOM_SECRET_KEY` | output from secret key command |
| MySQL password / DB name | from Databases tab |

5. **Save**

### Step 3.4 — Static files mapping

On the **Web** tab, **Static files** section, add:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/YOUR_USERNAME/Sama-Accounting/staticfiles` |
| `/media/` | `/home/YOUR_USERNAME/Sama-Accounting/media` |

Adjust paths if your project lives in a subfolder.

---

## Phase 4 — First-time setup (Bash console)

Activate the venv and go to the project:

```bash
workon sama-accounting
cd ~/Sama-Accounting
```

### Step 4.1 — Run migrations

**SQLite:**

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
export DJANGO_SECRET_KEY='paste-your-secret-key'
export DJANGO_ALLOWED_HOSTS='YOUR_USERNAME.pythonanywhere.com'
export DJANGO_DB_ENGINE=sqlite
export DJANGO_DB_PATH="/home/YOUR_USERNAME/Sama-Accounting/db.sqlite3"

python manage.py migrate
```

**MySQL:**

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
export DJANGO_SECRET_KEY='paste-your-secret-key'
export DJANGO_ALLOWED_HOSTS='YOUR_USERNAME.pythonanywhere.com'
export DJANGO_DB_ENGINE=mysql
export DJANGO_DB_NAME='YOUR_USERNAME$sama'
export DJANGO_DB_USER='YOUR_USERNAME'
export DJANGO_DB_PASSWORD='your-mysql-password'
export DJANGO_DB_HOST='YOUR_USERNAME.mysql.pythonanywhere-services.com'
export DJANGO_DB_PORT='3306'

python manage.py migrate
```

### Step 4.2 — Collect static files

```bash
python manage.py collectstatic --noinput
```

### Step 4.3 — Create roles (Admin, Accounting, Sales)

```bash
python manage.py seed_roles
```

### Step 4.4 — Create your admin user

```bash
python manage.py createsuperuser
```

Choose a **strong password** — this is your production login.

**Do not run** `seed_demo_data` or `seed_realistic_demo` on production.

### Step 4.5 — Optional: seed destinations

```bash
python manage.py seed_destinations
```

### Step 4.6 — Production check

```bash
python manage.py check --deploy
```

Fix any errors before continuing.

---

## Phase 5 — Go live

1. **Web** tab → green **Reload** button for your web app
2. Open `https://YOUR_USERNAME.pythonanywhere.com`
3. You should see the **login page**
4. Sign in with the superuser you created
5. Test: create a client, open dashboard, download a PDF

---

## Phase 6 — Post-launch checklist

- [ ] **Admin → Company branding** — confirm logo, address, phone, email for PDFs
- [ ] Upload logo if needed (`static/media/logo.png` is the fallback)
- [ ] Create staff users in **Admin → Users** and assign groups (Accounting / Sales)
- [ ] Confirm HTTPS works (PythonAnywhere provides this automatically)
- [ ] Test PDF download on a report and an invoice
- [ ] Back up `db.sqlite3` (SQLite) or use PythonAnywhere MySQL backups

---

## User roles

| Group | Access |
|-------|--------|
| **Admin** | Full access including Django admin |
| **Accounting** | Full ERP except sensitive admin areas |
| **Sales** | Clients, invoices (no cost/profit on PDFs) |

Run `python manage.py seed_roles` once if groups are missing.

---

## PDF exports on PythonAnywhere

The app tries **WeasyPrint** first, then falls back to **ReportLab** automatically.

- If PDFs look plain but complete → ReportLab fallback is active (normal on some PA setups)
- To try WeasyPrint system libraries (optional, advanced): PythonAnywhere support may need to enable Cairo/Pango — not required for go-live

---

## Updating the live site after code changes

On PythonAnywhere Bash console:

```bash
workon sama-accounting
cd ~/Sama-Accounting
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then **Web** tab → **Reload**.

---

## Troubleshooting

### “Bad Request (400)”

- `DJANGO_ALLOWED_HOSTS` must include `YOUR_USERNAME.pythonanywhere.com` (no `https://`)

### CSRF error on login

- Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://YOUR_USERNAME.pythonanywhere.com`

### Static files / CSS missing

- Run `collectstatic` again
- Check **Static files** mapping points to `staticfiles` folder (not `static`)

### Logo or uploads missing

- Check `/media/` static mapping on Web tab
- Ensure `media/` folder exists: `mkdir -p ~/Sama-Accounting/media`

### “Set DJANGO_SECRET_KEY…” on startup

- Secret key missing from WSGI file — add `os.environ["DJANGO_SECRET_KEY"] = "..."`

### Database errors with MySQL

- Database name must be `YOUR_USERNAME$something`
- Host must be `YOUR_USERNAME.mysql.pythonanywhere-services.com`
- Run migrations again after fixing WSGI env vars

### Error log

**Web** tab → **Log files** → **Error log**

---

## Security reminders

1. Never commit `.env` or production `SECRET_KEY` to GitHub
2. Never run demo seed commands on production
3. Use strong passwords for superuser and MySQL
4. Only trusted staff should have login accounts

---

## Quick reference — environment variables

| Variable | Required | Example |
|----------|----------|---------|
| `DJANGO_SECRET_KEY` | Yes | long random string |
| `DJANGO_ALLOWED_HOSTS` | Yes | `user.pythonanywhere.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Yes | `https://user.pythonanywhere.com` |
| `DJANGO_DEBUG` | Yes | `False` |
| `DJANGO_DB_ENGINE` | Yes | `sqlite` or `mysql` |
| `DJANGO_TIME_ZONE` | No | `Asia/Beirut` |

See `.env.example` for the full list.

---

When you are ready, tell me your **PythonAnywhere username** and whether you want **SQLite or MySQL**, and we can walk through each step together live.
