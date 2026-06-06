# PythonAnywhere deployment — Sama Accounting (ERP)

**ERP URL:** https://samatours2026.pythonanywhere.com  
**Project folder:** `~/Sama-Acc`  
**Virtualenv:** `sama-accounting`  
**Database:** `sama_acc` (user `sama_app`)

**Separate website (do not mix):** `~/SAMA-TOURS`, venv `sama-website`, DB `sama_website`, URL `main-samatours2026.pythonanywhere.com`

---

## A. One-time setup (do once)

### 1. Open Bash on PythonAnywhere

**Consoles** → **Bash**

### 2. Pull latest code

```bash
cd ~/Sama-Acc
git pull origin main
```

If `git pull` fails because of old manual edits:

```bash
git reset --hard HEAD
git pull origin main
```

### 3. Create secrets file

```bash
cp deploy/production.env.example deploy/production.env
nano deploy/production.env
```

Replace **only these two placeholders** with values from **Web tab → WSGI configuration file** (the **ERP** app, not SAMA-TOURS):

- `DJANGO_SECRET_KEY='...'`
- `DJANGO_DB_PASSWORD='...'`

Confirm DB settings match your ERP Postgres (`sama_acc` / `sama_app`, port `15298`).

Save: **Ctrl+O** → Enter → **Ctrl+X**

### 4. Optional — auto-reload after deploy

In **Web tab**, open the **ERP** WSGI file link and copy its path. Add to `deploy/production.env`:

```
PA_WSGI_FILE=/var/www/samatours2026_pythonanywhere_com_wsgi.py
```

(use your exact path from the Web tab)

### 5. Make script executable

```bash
chmod +x deploy/update.sh
```

You may need to run this again after some `git pull` updates if execute permission was lost.

---

## B. Every update (after you push from PC)

### On your PC

```powershell
cd "C:\Users\ME\Desktop\Acc System\Sama Accounting"
git add .
git commit -m "Your message"
git push origin main
```

### On PythonAnywhere (one command)

```bash
cd ~/Sama-Acc && ./deploy/update.sh
```

The script will:

1. Reset any old manual edits to **tracked** files on the server (`media/` uploads are untouched)
2. Load secrets from `deploy/production.env`
3. Pull from GitHub
4. Install Python packages
5. Check database connection
6. Apply **pending** migrations only (safe — keeps your accounting data)
7. Run `collectstatic`
8. Run `seed_destinations` (idempotent — adds missing rows only)
9. Reload the ERP app (if `PA_WSGI_FILE` is set)

If you did not set `PA_WSGI_FILE`, go to **Web tab → ERP app → Reload** (not the SAMA-TOURS website app).

### Check the site

https://samatours2026.pythonanywhere.com/

Hard refresh: **Ctrl+Shift+R**

---

## C. Troubleshooting

| Problem | Fix |
|--------|-----|
| `Missing deploy/production.env` | Run step A.3 |
| Secret key / password error | Edit `deploy/production.env` with real values from **ERP** WSGI |
| Site has no CSS | Run `./deploy/update.sh` again, then Reload on Web tab |
| `Virtualenv not found` | Run `workon sama-accounting` or `ls ~/.virtualenvs/` |
| Database error on migrate | Check DB password and that you use `sama_acc`, not `sama_website` |
| `Permission denied` on script | Run `chmod +x deploy/update.sh` |
| Wrong site updated | ERP = `~/Sama-Acc`; website = `~/SAMA-TOURS` — separate Reload buttons |

**Never delete and re-clone the repo for normal updates.**  
**Your uploaded files in `media/` are safe** — that folder is not in git.

**The script never runs:** `flush`, `reset_db`, `migrate --fake`, or any command that wipes data.
