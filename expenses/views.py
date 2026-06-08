import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts_core.list_utils import parse_date
from accounts_core.pdf_utils import render_or_pdf
from auditlog.utils import log_audit
from expenses.category_forms import ExpenseCategoryForm
from expenses.forms import OperatingExpenseForm
from expenses.models import OperatingExpense, OperatingExpenseAttachment
from purchases.models import ExpenseCategory


def _next_temp_expense_no():
    while True:
        candidate = f"TMP-OPEX-{uuid.uuid4().hex[:6].upper()}"
        if not OperatingExpense.objects.filter(expense_no=candidate).exists():
            return candidate


@login_required
def expense_list(request):
    from reporting.date_ranges import resolve_report_dates

    qs = OperatingExpense.objects.select_related("category").order_by("-expense_date", "-created_at")
    df, dt, _ = resolve_report_dates(request)
    cat = request.GET.get("category")
    if df:
        qs = qs.filter(expense_date__gte=df)
    if dt:
        qs = qs.filter(expense_date__lte=dt)
    if cat:
        qs = qs.filter(category_id=cat)
    return render_or_pdf(
        request,
        "expenses/expense_list.html",
        {
            "expenses": qs[:500],
            "date_from": df,
            "date_to": dt,
            "categories": ExpenseCategory.objects.filter(is_active=True).order_by("code"),
            "selected_category": cat,
            "pdf_report_title": "Operating Expenses",
        },
        "operating_expenses.pdf",
    )


@login_required
def expense_create(request):
    from datetime import date

    expense = OperatingExpense(expense_no=_next_temp_expense_no())
    if request.method == "POST":
        form = OperatingExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.expense_no = expense.expense_no
            exp.recalc_usd()
            exp.save()
            _save_attachments(request, exp)
            messages.success(request, f"Expense {exp.expense_no} created.")
            return redirect("expenses:expense_edit", expense_id=exp.id)
    else:
        form = OperatingExpenseForm(instance=expense, initial={"expense_date": date.today()})
    return render(
        request,
        "expenses/expense_form.html",
        {"form": form, "expense": expense, "attachments": [], "is_edit": False},
    )


@login_required
def expense_edit(request, expense_id):
    expense = get_object_or_404(OperatingExpense, pk=expense_id)
    if expense.status != OperatingExpense.Status.DRAFT:
        messages.warning(request, "Only draft expenses can be edited.")
        return redirect("expenses:expense_list")
    if request.method == "POST":
        form = OperatingExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.recalc_usd()
            exp.save()
            _save_attachments(request, exp)
            messages.success(request, f"Expense {exp.expense_no} updated.")
            return redirect("expenses:expense_edit", expense_id=exp.id)
    else:
        form = OperatingExpenseForm(instance=expense)
    return render(
        request,
        "expenses/expense_form.html",
        {
            "form": form,
            "expense": expense,
            "attachments": expense.attachments.all(),
            "is_edit": True,
        },
    )


def _save_attachments(request, expense):
    files = request.FILES.getlist("attachments")
    for f in files:
        if f.size > 10 * 1024 * 1024:
            messages.warning(request, f"Skipped {f.name}: file exceeds 10 MB.")
            continue
        OperatingExpenseAttachment.objects.create(
            expense=expense,
            file=f,
            original_name=f.name,
        )


@login_required
@require_http_methods(["POST"])
def expense_delete_attachment(request, expense_id, attachment_id):
    expense = get_object_or_404(OperatingExpense, pk=expense_id, status=OperatingExpense.Status.DRAFT)
    att = get_object_or_404(OperatingExpenseAttachment, pk=attachment_id, expense=expense)
    att.file.delete(save=False)
    att.delete()
    messages.success(request, "Attachment removed.")
    return redirect("expenses:expense_edit", expense_id=expense.id)


@login_required
def post_expense(request, expense_id):
    expense = get_object_or_404(OperatingExpense, pk=expense_id)
    try:
        expense.post(request.user)
        log_audit("POST_OPERATING_EXPENSE", expense, actor=request.user)
        messages.success(request, f"Expense {expense.expense_no} posted.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("expenses:expense_list")


@login_required
@require_http_methods(["POST"])
def void_expense(request, expense_id):
    expense = get_object_or_404(OperatingExpense, pk=expense_id)
    reason = request.POST.get("reason") or "Manual void"
    if expense.status != OperatingExpense.Status.POSTED:
        messages.error(request, "Only posted expenses can be voided.")
    else:
        from django.utils import timezone

        expense.status = OperatingExpense.Status.VOIDED
        expense.void_reason = reason
        expense.voided_at = timezone.now()
        expense.save()
        messages.success(request, f"Expense {expense.expense_no} voided.")
    return redirect("expenses:expense_list")


@login_required
def expense_category_list(request):
    qs = ExpenseCategory.objects.order_by("code")
    if request.GET.get("show_inactive") != "1":
        qs = qs.filter(is_active=True)
    return render(
        request,
        "expenses/category_list.html",
        {"categories": qs},
    )


@login_required
def expense_category_create(request):
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Category {cat.name} created.")
            return redirect("expenses:expense_category_edit", category_id=cat.id)
    else:
        form = ExpenseCategoryForm(initial={"is_active": True})
    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "category": None, "is_edit": False},
    )


@login_required
def expense_category_edit(request, category_id):
    category = get_object_or_404(ExpenseCategory, pk=category_id)
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category {category.name} updated.")
            return redirect("expenses:expense_category_list")
    else:
        form = ExpenseCategoryForm(instance=category)
    return render(
        request,
        "expenses/category_form.html",
        {"form": form, "category": category, "is_edit": True},
    )


@login_required
@require_http_methods(["POST"])
def expense_category_deactivate(request, category_id):
    category = get_object_or_404(ExpenseCategory, pk=category_id)
    category.is_active = False
    category.save(update_fields=["is_active"])
    messages.success(request, f"Category {category.name} deactivated.")
    return redirect("expenses:expense_category_list")


@login_required
@require_http_methods(["POST"])
def expense_category_delete(request, category_id):
    category = get_object_or_404(ExpenseCategory, pk=category_id)
    try:
        name = category.name
        category.delete()
        messages.success(request, f"Category {name} deleted.")
        return redirect("expenses:expense_category_list")
    except ProtectedError:
        messages.error(request, "Cannot delete: category is used on expenses. Deactivate instead.")
        return redirect("expenses:expense_category_edit", category_id=category_id)


@login_required
@require_http_methods(["POST"])
def expense_category_quick_create(request):
    import json

    from django.http import JsonResponse

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    code = (payload.get("code") or "").strip().upper()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        return JsonResponse({"error": "Code and name are required."}, status=400)
    if ExpenseCategory.objects.filter(code=code).exists():
        return JsonResponse({"error": f"Category code {code} already exists."}, status=400)

    cat = ExpenseCategory.objects.create(code=code, name=name, is_active=True)
    return JsonResponse({"id": str(cat.id), "code": cat.code, "name": cat.name})
