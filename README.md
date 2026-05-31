# Sama Accounting (Sama Tours ERP)

Django accounting and operations system for travel agencies: clients, invoices, suppliers, treasury, expenses, and reporting.

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_roles
python manage.py runserver
```

Optional demo data: `python manage.py seed_realistic_demo` (local only).

## Production (PythonAnywhere)

**Full go-live guide:** [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md)

Summary:

1. Push to GitHub
2. Clone on PythonAnywhere, create venv, `pip install -r requirements.txt`
3. Configure WSGI from `deploy/pythonanywhere_wsgi.py.example`
4. Map `/static/` and `/media/` on the Web tab
5. `migrate`, `collectstatic`, `seed_roles`, `createsuperuser`
6. Reload web app

Copy `.env.example` to `.env` for local production testing.

## Roles

Run once: `python manage.py seed_roles`

- **Admin** — full access  
- **Accounting** — full ERP  
- **Sales** — sales-facing screens (no cost/profit on invoice PDFs)
