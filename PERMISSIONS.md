# User Roles & Permissions — Sama Accounting

## Overview

The system uses **Django Groups** (role-based) for baseline model permissions, plus **view-level checks** in Python code for sensitive UI behavior. Business **Employee** records (salesman on invoices) are separate from login roles.

| Layer | Purpose |
|-------|---------|
| Django `User` + `Group` | Login, Admin permissions, API auth |
| `UserProfile` | Flags such as `is_main_accountant` (default invoice employee) |
| `Employee` | Who sold/serviced work (commission reporting) |
| View decorators | `@login_required` on sales, treasury, expenses |
| Group checks in views | Sales hides cost; Accounting/Admin can adjust posted invoices |

**Seed roles:** `python manage.py seed_roles`

---

## Roles

### Admin

| Item | Detail |
|------|--------|
| **Group name** | `Admin` |
| **Django permissions** | All model permissions (`Permission.objects.all()`) |
| **Pages** | Full access via Django Admin; all operational modules when logged in |
| **Actions** | Create, view, edit, delete (via admin); post/void documents; adjust invoices; manage users/groups |
| **Restrictions** | None at permission level |
| **Privileges** | Superuser-equivalent group permissions; only role with full admin CRUD |

### Accounting

| Item | Detail |
|------|--------|
| **Group name** | `Accounting` |
| **Pages** | Sales invoices (view/change), supplier bills (view/change), payments (view/add/change), AR/AP allocations (view/add) |
| **Allowed actions** | Edit draft/posted payments; create allocations; view and change invoices/bills; **adjust posted invoices** (with view check) |
| **Cannot** | Full admin; no explicit delete permissions in seed |
| **View enforcement** | `adjust_invoice`, `can_adjust` on invoice detail require Accounting, Admin, or superuser |

**Codenames seeded:** `view_salesinvoice`, `change_salesinvoice`, `view_supplierbill`, `change_supplierbill`, `view_payment`, `add_payment`, `change_payment`, `view_arallocation`, `add_arallocation`, `view_apallocation`, `add_apallocation`

### Sales

| Item | Detail |
|------|--------|
| **Group name** | `Sales` |
| **Pages** | Sales invoices (view/add/change), invoice lines, clients (view) |
| **Allowed actions** | Create and edit **draft** invoices; cannot see **cost_price** on lines |
| **Cannot** | Adjust posted invoices; treasury; supplier bills; post/void (unless also given other groups) |
| **View enforcement** | `can_view_cost = not user.groups.filter(name="Sales")` on invoice create/edit |

**Codenames seeded:** `view_salesinvoice`, `add_salesinvoice`, `change_salesinvoice`, `view_salesinvoiceline`, `add_salesinvoiceline`, `change_salesinvoiceline`, `view_client`

---

## Module access by URL (web UI)

| Module | URL prefix | Login required | Notes |
|--------|------------|----------------|-------|
| Dashboard | `/` | No | Consider restricting in production |
| Clients / Suppliers | `/clients/`, `/suppliers/` | No | Lists + PDF export |
| Catalog | `/catalog/` | No | Service types/instances |
| Sales invoices | `/sales/` | **Yes** | Create, edit, post, void, adjust |
| Supplier bills | `/purchases/` | **Yes** | Manual bills + OPEX lines |
| Treasury | `/treasury/` | **Yes** | Payments, allocations, reconcile |
| Operating expenses | `/expenses/` | **Yes** | Standalone OPEX module |
| Reporting | `/reporting/` | No | Statements, P&L, aging, salesman reports |
| API | `/api/` | **Yes** (DRF `IsAuthenticated`) | REST for invoices, bills, payments, etc. |
| Django Admin | `/admin/` | Staff/superuser | Full model admin |

---

## Authorization enforcement

1. **`@login_required`** — Sales, purchases, treasury, expenses views redirect to `LOGIN_URL` (`/admin/login/`).
2. **Group name checks** — Inline in views (e.g. Sales vs Accounting), not `permission_required` decorators.
3. **Model `clean()` / `save()`** — Payments, allocations, invoices block invalid state (posted immutability, allocation limits).
4. **DRF** — Session/basic auth; serializers mirror post/void rules for invoices.
5. **Django Admin** — Respects group permissions for Accounting/Sales; Admin group has all permissions.

---

## Employee vs User

- **`Employee`**: `SALES`, `ACCOUNTING`, `ADMIN` — used on `SalesInvoice.sales_employee` and `SalesInvoiceLine.line_employee` for salesman reports.
- **`User` → Group**: controls what the logged-in person can do in the app.
- A user may be linked to an `Employee` via `Employee.user` (optional).

---

## Gaps & recommendations

- Reporting, dashboard, and catalog are **not** behind `@login_required` — add middleware or decorators for production.
- Group permissions are seeded but **most views do not call** `user.has_perm()`; enforcement is primarily login + explicit group name checks.
- **Credit notes** exist in the database/admin only (no web UI).
- Run `seed_roles` after adding new models so Accounting can manage expenses if desired.
