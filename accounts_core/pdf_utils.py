"""
PDF export utilities.

Tabular reports are normalized to pdf_table_rows + pdf_table_headers so both
WeasyPrint (pdf/table_report.html) and ReportLab fallback render the same data.
"""
from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from accounts_core.branding import get_company_branding

STATEMENT_HEADERS = ["Date", "Reference", "Description", "Type", "Debit", "Credit", "Balance"]
STATEMENT_HEADERS_WITH_PARTY = [
    "Account",
    "Date",
    "Reference",
    "Description",
    "Type",
    "Debit",
    "Credit",
    "Balance",
]

# Column headers that should get extra width and word-wrap in PDF tables.
_PDF_WIDE_HEADER_KEYS = (
    "name",
    "description",
    "client",
    "supplier",
    "party",
    "note",
)


def _format_cell(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _party_label(payment):
    if payment.client_id:
        return payment.client.name_en
    if payment.supplier_id:
        return payment.supplier.name
    return payment.party_name or "Other"


# ---------------------------------------------------------------------------
# Row flatteners: convert view context into printable table rows
# ---------------------------------------------------------------------------

def _flatten_trial_balance_row(r):
    return [
        _format_cell(r.get("account")),
        _format_cell(r.get("name")),
        _format_cell(r.get("curr")),
        _format_cell(r.get("tot_dr")),
        _format_cell(r.get("tot_cr")),
        _format_cell(r.get("bal_dr")),
        _format_cell(r.get("bal_cr")),
    ]


def _pdf_table_row_entry(cells, kind=None):
    if kind:
        return {"cells": cells, "kind": kind}
    return cells


def _pdf_row_cells(row):
    if isinstance(row, dict) and "cells" in row:
        return row["cells"]
    return row


def _pdf_row_kind(row, index=0, kinds=None):
    if isinstance(row, dict) and row.get("kind"):
        return row["kind"]
    if kinds and index < len(kinds):
        return kinds[index]
    return None


def _income_statement_period_subtitle(context):
    df = context.get("date_from")
    dt = context.get("date_to")
    parts = []
    if df and dt:
        parts.append(f"{df.strftime('%d/%m/%Y')} – {dt.strftime('%d/%m/%Y')}")
    elif df:
        parts.append(f"From {df.strftime('%d/%m/%Y')}")
    elif dt:
        parts.append(f"Until {dt.strftime('%d/%m/%Y')}")
    else:
        parts.append("All dates")
    preset = (context.get("period_label") or "").strip()
    if preset and preset not in parts[0]:
        parts.append(preset)
    return " · ".join(parts)


def _prepare_income_statement_pdf(context):
    """Rich PDF layout for activity trial balance / income statement."""
    rows = context.get("rows") or []
    subtitle = _income_statement_period_subtitle(context)

    context["pdf_stat_cards"] = [
        {"label": "Sales Revenue", "value": _format_cell(context.get("sales_total")), "kind": "credit"},
        {"label": "Cost of Sales", "value": _format_cell(context.get("cogs_total")), "kind": "debit"},
        {"label": "Gross Profit", "value": _format_cell(context.get("gross_profit")), "kind": "balance"},
        {"label": "Operating Expenses", "value": _format_cell(context.get("opex_total")), "kind": "debit"},
        {"label": "Net Profit", "value": _format_cell(context.get("net_profit")), "kind": "balance"},
    ]
    context["pdf_section_title"] = "Income Statement Detail"
    context["pdf_section_subtitle"] = subtitle
    note_parts = []
    if context.get("pdf_account_range"):
        note_parts.append(str(context["pdf_account_range"]))
    note_parts.append("Amounts in USD. Includes posted sales invoices, service COGS, and operating expenses.")
    context["pdf_note"] = " ".join(note_parts)

    context["pdf_table_headers"] = [
        "Account",
        "Name",
        "Curr",
        "Total Debit",
        "Total Credit",
        "Balance Debit",
        "Balance Credit",
    ]
    context["pdf_table_rows"] = [
        _pdf_table_row_entry(
            _flatten_trial_balance_row(r),
            kind="summary" if r.get("is_summary") else "detail",
        )
        for r in rows
    ]
    context["pdf_footer_row"] = [
        "Period totals",
        "",
        "",
        _format_cell(context.get("tot_dr")),
        _format_cell(context.get("tot_cr")),
        _format_cell(context.get("bal_dr")),
        _format_cell(context.get("bal_cr")),
    ]
    context["pdf_totals"] = [
        ("Sales revenue", _format_cell(context.get("sales_total"))),
        ("Cost of sales (COGS)", _format_cell(context.get("cogs_total"))),
        ("Gross profit", _format_cell(context.get("gross_profit"))),
        ("Operating expenses", _format_cell(context.get("opex_total"))),
        ("Net profit", _format_cell(context.get("net_profit"))),
    ]
    context["pdf_totals_closing_last"] = True
    context["pdf_numeric_column_indexes"] = [3, 4, 5, 6]
    context["pdf_description_column_index"] = 1
    context["pdf_hide_subtitle_in_body"] = True
    context["pdf_currency"] = context.get("pdf_currency") or "USD"
    _apply_pdf_table_layout(context)
    return context


def _statement_description(r):
    desc = (r.get("description") or "").strip()
    typ = (r.get("type") or "").strip()
    if desc and typ and typ not in desc:
        return f"{typ} — {desc}"
    return desc or typ or ""


def _statement_type_label(r):
    debit = Decimal(str(r.get("debit") or 0))
    credit = Decimal(str(r.get("credit") or 0))
    if debit > 0:
        return "DEBIT"
    if credit > 0:
        return "CREDIT"
    return (r.get("type") or "").upper()


def _flatten_statement_row(r):
    return [
        _format_cell(r.get("date")),
        _format_cell(r.get("ref")),
        _statement_description(r),
        _statement_type_label(r),
        _format_cell(r.get("debit")),
        _format_cell(r.get("credit")),
        _format_cell(r.get("running_balance")),
    ]


def _flatten_statement_row_with_party(r, party_label):
    return [
        party_label,
        _format_cell(r.get("date")),
        _format_cell(r.get("ref")),
        _statement_description(r),
        _statement_type_label(r),
        _format_cell(r.get("debit")),
        _format_cell(r.get("credit")),
        _format_cell(r.get("running_balance")),
    ]


def _statement_pdf_meta(context, rows, *, with_party=False):
    total_dr = Decimal("0")
    total_cr = Decimal("0")
    for r in rows:
        total_dr += Decimal(str(r.get("debit") or 0))
        total_cr += Decimal(str(r.get("credit") or 0))
    closing = rows[-1].get("running_balance") if rows else Decimal("0")
    if with_party:
        context["pdf_table_headers"] = STATEMENT_HEADERS_WITH_PARTY
        context["pdf_numeric_column_indexes"] = [5, 6, 7]
        context["pdf_ref_column_index"] = 2
        context["pdf_description_column_index"] = 3
        context["pdf_badge_column_index"] = 4
        context["pdf_column_widths"] = ["13%", "9%", "15%", "20%", "11%", "11%", "10%", "11%"]
    else:
        context["pdf_table_headers"] = STATEMENT_HEADERS
        context["pdf_numeric_column_indexes"] = [4, 5, 6]
        context["pdf_ref_column_index"] = 1
        context["pdf_description_column_index"] = 2
        context["pdf_badge_column_index"] = 3
        context["pdf_column_widths"] = ["10%", "16%", "24%", "12%", "12%", "11%", "15%"]
    context["pdf_totals"] = [
        ("Total Debit", _format_cell(total_dr)),
        ("Total Credit", _format_cell(total_cr)),
        ("Closing Balance", _format_cell(closing)),
    ]
    context["pdf_stat_cards"] = [
        {"label": "Total Debit", "value": _format_cell(total_dr), "kind": "debit"},
        {"label": "Total Credit", "value": _format_cell(total_cr), "kind": "credit"},
        {"label": "Closing Balance", "value": _format_cell(closing), "kind": "balance"},
    ]
    context.setdefault("pdf_section_title", "Transaction Details")
    df = context.get("date_from")
    dt = context.get("date_to")
    if df and dt:
        period_text = f"From {df.strftime('%d/%m/%Y')} to {dt.strftime('%d/%m/%Y')}"
    elif df:
        period_text = f"From {df.strftime('%d/%m/%Y')}"
    elif dt:
        period_text = f"Until {dt.strftime('%d/%m/%Y')}"
    else:
        period_text = "All dates"
    context["pdf_section_subtitle"] = period_text
    context["pdf_totals_closing_last"] = True
    context["pdf_currency"] = context.get("pdf_currency") or "USD"
    context["pdf_hide_subtitle_in_body"] = True


def _flatten_all_clients_row(r):
    party = f"{r.get('client_name', '')} ({r.get('client_code', '')})"
    return _flatten_statement_row_with_party(r, party)


def _flatten_ar_aging_row(r):
    inv = r.get("invoice")
    return [
        inv.invoice_no if inv else "",
        inv.client.name_en if inv and inv.client_id else "",
        _format_cell(r.get("due")),
        _format_cell(r.get("not_due")),
        _format_cell(r.get("b0_30")),
        _format_cell(r.get("b31_60")),
        _format_cell(r.get("b61_90")),
        _format_cell(r.get("b90_plus")),
    ]


def _flatten_ap_aging_row(r):
    bill = r.get("bill")
    return [
        bill.bill_no if bill else "",
        bill.supplier.name if bill and bill.supplier_id else "",
        _format_cell(r.get("due")),
        _format_cell(r.get("not_due")),
        _format_cell(r.get("b0_30")),
        _format_cell(r.get("b31_60")),
        _format_cell(r.get("b61_90")),
        _format_cell(r.get("b90_plus")),
    ]


def _flatten_cash_row(r):
    acc = r.get("account")
    return [
        acc.name if acc else "",
        acc.currency if acc else "",
        _format_cell(r.get("expected_closing")),
    ]


def _flatten_salesman_detailed_row(r):
    return [
        _format_cell(r.get("invoice_no")),
        _format_cell(r.get("client_name")),
        _format_cell(r.get("selling")),
        _format_cell(r.get("cost")),
        _format_cell(r.get("profit")),
    ]


def _flatten_opex_category_row(r):
    return [
        _format_cell(r.get("expense_category__code") or "UNCAT"),
        _format_cell(r.get("expense_category__name") or "Uncategorized"),
        _format_cell(r.get("total")),
    ]


def _flatten_invoice(inv):
    return [
        inv.invoice_no or "",
        inv.client.name_en if inv.client_id else "",
        _format_cell(inv.issue_date),
        inv.status,
        f"{_format_cell(inv.grand_total)} {inv.currency}",
        f"{_format_cell(inv.grand_total_usd)} USD",
        f"{_format_cell(inv.total_line_cost())} {inv.currency}",
        f"{_format_cell(inv.profit_amount)} USD",
    ]


def _prepare_invoice_document_pdf(context):
    """Statement-style PDF for a single sales invoice."""
    invoice = context.get("invoice")
    lines = context.get("lines")
    if not invoice or lines is None:
        return
    show_costs = context.get("show_costs")
    headers = ["Date", "Service", "Destination"]
    if show_costs:
        headers.append("Supplier")
    headers.extend(["Qty", "Sell"])
    if show_costs:
        headers.extend(["Cost", "Cost USD"])
    headers.append("Description")

    table_rows = []
    for line in lines:
        row = [
            _format_cell(line.effective_service_date() if callable(getattr(line, "effective_service_date", None)) else line.effective_service_date),
            line.service_type.name if line.service_type_id else "—",
            line.destination.name if line.destination_id else "—",
        ]
        if show_costs:
            row.append(line.supplier.name if line.supplier_id else "—")
        row.extend([_format_cell(line.qty), _format_cell(line.sell_price)])
        if show_costs:
            row.extend([_format_cell(line.cost_price), _format_cell(line.cost_price_usd)])
        desc = line.statement_description() if callable(getattr(line, "statement_description", None)) else ""
        row.append(desc or "—")
        table_rows.append(row)

    numeric_start = 3 if not show_costs else 4
    numeric_indexes = list(range(numeric_start, numeric_start + (4 if show_costs else 2)))
    context["pdf_table_headers"] = headers
    context["pdf_table_rows"] = table_rows
    context["pdf_numeric_column_indexes"] = numeric_indexes
    context["pdf_description_column_index"] = len(headers) - 1
    context["pdf_wrap_column_indexes"] = [len(headers) - 1]
    context["pdf_hide_subtitle_in_body"] = True

    context["pdf_account_name"] = invoice.client.name_en if invoice.client_id else "Draft"
    context["pdf_account_id"] = invoice.invoice_no or "—"

    cards = [
        {"label": "Total Selling", "value": f"{_format_cell(invoice.grand_total)} {invoice.currency}", "kind": "balance"},
    ]
    if show_costs:
        cards.append({"label": "Total Cost (USD)", "value": _format_cell(invoice.total_line_cost_usd()), "kind": "debit"})
        cards.append({"label": "Profit (USD)", "value": _format_cell(invoice.profit_amount), "kind": "credit"})
    else:
        if invoice.grand_total_usd:
            cards.append({"label": "Total (USD)", "value": f"{_format_cell(invoice.grand_total_usd)} USD", "kind": "credit"})
        cards.append({
            "label": "Type of Service",
            "value": invoice.get_package_type_display() if invoice.package_type else "—",
            "kind": "neutral",
        })
    context["pdf_stat_cards"] = cards
    context["pdf_section_title"] = "Invoice Details"
    context["pdf_section_subtitle"] = "Services billed on this invoice."
    context["pdf_hide_period"] = True

    totals = [("Grand total", f"{_format_cell(invoice.grand_total)} {invoice.currency}")]
    if invoice.grand_total_usd:
        totals.append(("Total (USD)", f"{_format_cell(invoice.grand_total_usd)} USD"))
    if show_costs:
        totals.append(("Total cost (USD)", _format_cell(invoice.total_line_cost_usd())))
        totals.append(("Profit (USD)", _format_cell(invoice.profit_amount)))
    context["pdf_totals"] = totals
    context["pdf_totals_closing_last"] = True
    _apply_pdf_table_layout(context)


def _prepare_payment_document_pdf(context):
    """Standardized payment receipt PDF using the shared table-report layout."""
    payment = context.get("payment")
    if not payment:
        return
    party = _party_label(payment)
    direction = payment.get_direction_display() or payment.direction
    context["pdf_table_headers"] = ["Detail", "Information"]
    context["pdf_table_rows"] = [
        ["Receipt number", payment.receipt_no or "—"],
        ["Reference", payment.reference or "—"],
        ["Party", party],
        ["Date", _format_cell(payment.date)],
        ["Money account", payment.money_account.name if payment.money_account_id else "—"],
        ["Direction", direction],
        ["Payment method", getattr(payment, "payment_method", "") or "—"],
        ["Status", payment.status],
        ["Note", payment.note or "—"],
    ]
    context["pdf_numeric_column_indexes"] = []
    context["pdf_description_column_index"] = 1
    context["pdf_wrap_column_indexes"] = [1]
    context["pdf_account_name"] = party
    context["pdf_account_id"] = payment.receipt_no or "—"
    context["pdf_stat_cards"] = [
        {"label": "Amount", "value": f"{_format_cell(payment.amount)} {payment.currency}", "kind": "balance"},
        {"label": "Direction", "value": direction, "kind": "credit" if payment.direction == "IN" else "debit"},
        {"label": "Status", "value": payment.status, "kind": "neutral"},
    ]
    context["pdf_section_title"] = "Receipt Details"
    context["pdf_section_subtitle"] = "Payment information for this receipt."
    context["pdf_hide_period"] = True
    context["pdf_totals"] = [("Paid amount", f"{_format_cell(payment.amount)} {payment.currency}")]
    context["pdf_totals_closing_last"] = True
    context["pdf_hide_subtitle_in_body"] = True
    _apply_pdf_table_layout(context)


def _flatten_payment(p):
    return [
        p.receipt_no,
        p.reference or "",
        _party_label(p),
        p.money_account.name if p.money_account_id else "",
        p.direction,
        f"{_format_cell(p.amount)} {p.currency}",
        (p.note or "")[:80],
        p.status,
    ]


def _flatten_bill(b):
    return [
        b.bill_no,
        b.supplier.name if b.supplier_id else "",
        _format_cell(b.bill_date),
        b.status,
        f"{_format_cell(b.grand_total)} {b.currency}",
    ]


def _flatten_expense(e):
    return [
        e.expense_no or "",
        _format_cell(e.expense_date),
        e.category.name if e.category_id else "",
        (e.description or "")[:60],
        f"{_format_cell(e.amount)} {e.currency}",
        _format_cell(e.amount_usd),
        e.status,
    ]


def _flatten_client(c):
    return [
        c.client_code,
        c.name_en,
        c.type,
        _format_cell(c.date_of_birth) if c.date_of_birth else "-",
        c.whatsapp or "-",
        _format_cell(c.outstanding_receivable),
    ]


def _flatten_supplier(s):
    return [
        s.supplier_code,
        s.name,
        s.type,
        s.default_currency,
    ]


def _apply_pdf_table_layout(context):
    """Column widths and wrap indexes so long text stays inside cells (WeasyPrint + ReportLab)."""
    headers = context.get("pdf_table_headers") or []
    if not headers:
        return
    numeric = set(context.get("pdf_numeric_column_indexes") or [])
    ref_idx = context.get("pdf_ref_column_index", -1)
    desc_idx = context.get("pdf_description_column_index", -1)

    weights = []
    wrap_indexes = []
    for i, header in enumerate(headers):
        h = (header or "").lower()
        if i in numeric:
            weights.append(0.9)
        elif i == desc_idx or h == "account" or any(k in h for k in _PDF_WIDE_HEADER_KEYS):
            weights.append(2.8)
            wrap_indexes.append(i)
        elif i == ref_idx or "date" in h or "status" in h:
            weights.append(1.1)
        elif "curr" in h or "code" in h or "invoice" in h or "bill" in h or "receipt" in h:
            weights.append(1.2)
        else:
            weights.append(1.4)
            wrap_indexes.append(i)

    total_w = sum(weights) or 1
    context["pdf_column_widths"] = [f"{w / total_w * 100:.2f}%" for w in weights]
    context["pdf_wrap_column_indexes"] = sorted(set(wrap_indexes))


def prepare_pdf_export(context):
    """
    Populate pdf_table_headers, pdf_table_rows, pdf_footer_row for PDF rendering.
    Call after build_pdf_context when format=pdf.
    """
    if context.get("pdf_table_rows"):
        _apply_pdf_table_layout(context)
        return context

    if context.get("invoice") and context.get("lines") is not None:
        _prepare_invoice_document_pdf(context)
        return context

    if context.get("payment"):
        _prepare_payment_document_pdf(context)
        return context

    if context.get("pdf_income_statement"):
        _prepare_income_statement_pdf(context)
        return context

    rows = context.get("rows")
    if rows and isinstance(rows, list) and rows:
        first = rows[0]
        if isinstance(first, dict):
            if "tot_dr" in first and "account" in first:
                context["pdf_table_headers"] = [
                    "Account", "Name", "Curr", "Total Debit", "Total Credit", "Balance Debit", "Balance Credit"
                ]
                context["pdf_table_rows"] = [_flatten_trial_balance_row(r) for r in rows]
                if context.get("tot_dr") is not None:
                    context["pdf_footer_row"] = [
                        "Totals", "", "",
                        _format_cell(context["tot_dr"]),
                        _format_cell(context["tot_cr"]),
                        _format_cell(context["bal_dr"]),
                        _format_cell(context["bal_cr"]),
                    ]
                    if context.get("total_balance") is not None:
                        context["pdf_table_headers"].append("Total Balance")
                        context["pdf_table_rows"] = [
                            list(r) + [""] for r in context["pdf_table_rows"]
                        ]
                        context["pdf_footer_row"].append(
                            _format_cell(context["total_balance"])
                        )
                context["pdf_numeric_column_indexes"] = list(
                    range(3, len(context["pdf_table_headers"]))
                )
            elif "running_balance" in first:
                context["pdf_table_rows"] = [_flatten_statement_row(r) for r in rows]
                _statement_pdf_meta(context, rows, with_party=False)
            elif "selling" in first and "invoice_no" in first:
                context["pdf_table_headers"] = [
                    "Invoice ID", "Client Name", "Total Selling", "Total Cost", "Profit"
                ]
                context["pdf_table_rows"] = [_flatten_salesman_detailed_row(r) for r in rows]
                if context.get("total_selling") is not None:
                    context["pdf_footer_row"] = [
                        "Totals", "",
                        _format_cell(context.get("total_selling")),
                        _format_cell(context.get("total_cost")),
                        _format_cell(context.get("total_profit")),
                    ]
            elif "expense_category__code" in first or ("total" in first and "expense_category__name" in first):
                context["pdf_table_headers"] = ["Category Code", "Category Name", "Total USD"]
                context["pdf_table_rows"] = [_flatten_opex_category_row(r) for r in rows]
            elif "invoice" in first and "due" in first:
                context["pdf_table_headers"] = [
                    "Invoice", "Client", "Total Due", "Not Due", "0-30", "31-60", "61-90", "90+"
                ]
                context["pdf_table_rows"] = [_flatten_ar_aging_row(r) for r in rows]
            elif "bill" in first and "due" in first:
                context["pdf_table_headers"] = [
                    "Bill", "Supplier", "Total Due", "Not Due", "0-30", "31-60", "61-90", "90+"
                ]
                context["pdf_table_rows"] = [_flatten_ap_aging_row(r) for r in rows]
            elif "account" in first and "expected_closing" in first:
                context["pdf_table_headers"] = ["Account", "Currency", "Expected Closing"]
                context["pdf_table_rows"] = [_flatten_cash_row(r) for r in rows]
        _apply_pdf_table_layout(context)
        return context

    if context.get("invoices"):
        context["pdf_table_headers"] = [
            "Invoice", "Client", "Date", "Status", "Total (doc)", "Total (USD)", "Cost", "Profit (USD)"
        ]
        context["pdf_table_rows"] = [_flatten_invoice(i) for i in context["invoices"]]
        context["pdf_numeric_column_indexes"] = [4, 5, 6, 7]

    elif context.get("payments"):
        context["pdf_table_headers"] = [
            "Receipt", "Ref No", "Party", "Account", "Direction", "Amount", "Note", "Status"
        ]
        context["pdf_table_rows"] = [_flatten_payment(p) for p in context["payments"]]
        context["pdf_numeric_column_indexes"] = [5]
        context["pdf_ref_column_index"] = 1

    elif context.get("bills"):
        context["pdf_table_headers"] = ["Bill", "Supplier", "Date", "Status", "Total"]
        context["pdf_table_rows"] = [_flatten_bill(b) for b in context["bills"]]
        context["pdf_numeric_column_indexes"] = [4]

    elif context.get("expenses"):
        context["pdf_table_headers"] = [
            "No", "Date", "Category", "Description", "Amount", "USD", "Status"
        ]
        context["pdf_table_rows"] = [_flatten_expense(e) for e in context["expenses"]]
        context["pdf_numeric_column_indexes"] = [4, 5]
        context["pdf_description_column_index"] = 3

    elif context.get("clients"):
        context["pdf_table_headers"] = ["Code", "Name", "Type", "Date of birth", "Phone", "Outstanding A/R"]
        context["pdf_table_rows"] = [_flatten_client(c) for c in context["clients"]]
        context["pdf_numeric_column_indexes"] = [5]

    elif context.get("suppliers"):
        context["pdf_table_headers"] = ["Code", "Name", "Type", "Currency"]
        context["pdf_table_rows"] = [_flatten_supplier(s) for s in context["suppliers"]]

    # Brief salesman / dashboard summary cards
    if context.get("total_revenue") is not None and context.get("employee"):
        context["pdf_summary_cards"] = [
            ("Services sold", context.get("total_services", 0)),
            ("Clients handled", context.get("total_clients", 0)),
            ("Invoices handled", context.get("total_invoices", 0)),
            ("Revenue (USD)", _format_cell(context.get("total_revenue"))),
            ("Profit (USD)", _format_cell(context.get("total_profit"))),
        ]
        return context

    summary_keys = [
        ("Posted Sales (USD)", "posted_invoices_total"),
        ("Posted Purchases", "posted_bills_total"),
        ("Posted Payments", "posted_payments_total"),
        ("COGS", "posted_cogs_total"),
        ("Operating Expenses (USD)", "total_opex"),
        ("Net Profit Estimate", "net_profit_estimate"),
    ]
    cards = [(label, _format_cell(context[key])) for label, key in summary_keys if key in context]
    if cards:
        context["pdf_summary_cards"] = cards

    if not context.get("pdf_table_rows") and not context.get("pdf_summary_cards"):
        tabular_context = any(
            [
                context.get("rows") is not None,
                context.get("invoices"),
                context.get("payments"),
                context.get("bills"),
                context.get("expenses"),
                context.get("clients"),
                context.get("suppliers"),
                context.get("total_revenue") is not None and context.get("employee"),
                context.get("posted_invoices_total") is not None,
            ]
        )
        if tabular_context:
            context["pdf_empty_message"] = "No data for the selected filters."

    if context.get("pdf_table_rows") and context.get("pdf_table_headers"):
        _apply_pdf_table_layout(context)

    return context


def build_pdf_context(request, filename, context=None):
    ctx = dict(context or {})
    export_fmt = (request.GET.get("format") or "").lower()
    is_pdf = export_fmt == "pdf"
    is_xlsx = export_fmt == "xlsx"
    company = get_company_branding(request)
    base = {
        "is_pdf": is_pdf or is_xlsx,
        "pdf_filename": filename,
        "pdf_generated_on": date.today(),
        "company": company,
        "pdf_currency": ctx.get("pdf_currency") or company.get("default_currency") or "USD",
    }
    merged = {**base, **ctx}
    if not merged.get("pdf_report_title"):
        merged["pdf_report_title"] = filename.replace(".pdf", "").replace("_", " ").title()
    merged.setdefault("pdf_numeric_column_indexes", [])
    merged.setdefault("pdf_wrap_column_indexes", [])
    merged.setdefault("pdf_column_widths", [])
    merged.setdefault("pdf_ref_column_index", -1)
    merged.setdefault("pdf_description_column_index", -1)
    merged.setdefault("pdf_badge_column_index", -1)
    merged.setdefault("pdf_hide_subtitle_in_body", False)
    if is_pdf or is_xlsx:
        if not merged.get("date_from") and not merged.get("date_to"):
            from reporting.date_ranges import resolve_report_dates

            df, dt, period_label = resolve_report_dates(request)
            merged.setdefault("date_from", df)
            merged.setdefault("date_to", dt)
            merged.setdefault("period_label", period_label)
        if merged.get("date_from") or merged.get("date_to"):
            df = merged.get("date_from")
            dt = merged.get("date_to")
            period_note = ""
            if df and dt:
                period_note = f"Period: {df.strftime('%d/%m/%Y')} – {dt.strftime('%d/%m/%Y')}"
            elif df:
                period_note = f"From: {df.strftime('%d/%m/%Y')}"
            elif dt:
                period_note = f"Until: {dt.strftime('%d/%m/%Y')}"
            sub = (merged.get("pdf_report_subtitle") or "").strip()
            if period_note and period_note not in sub:
                merged["pdf_report_subtitle"] = f"{sub} | {period_note}" if sub else period_note
        prepare_pdf_export(merged)
    return merged


def _reportlab_cell_paragraph(text, style):
    from xml.sax.saxutils import escape

    from reportlab.platypus import Paragraph

    safe = escape(str(text or ""))
    return Paragraph(safe, style)


# ----------------------------------------------------------------------------
# ReportLab corporate renderer (matches the Statement of Account design)
# ----------------------------------------------------------------------------

RL_NAVY = "#0e2a55"
RL_NAVY_SOFT = "#1f4a8a"
RL_TABLE_HEAD = "#143a6b"
RL_MUTED = "#5b6b82"
RL_INK = "#25324a"
RL_LINE = "#e2e8f0"
RL_DEBIT = "#d23b3b"
RL_DEBIT_BG = "#fdecec"
RL_CREDIT = "#1f9d57"
RL_CREDIT_BG = "#e8f6ef"
RL_BALANCE_BG = "#eef2fb"
RL_NEUTRAL_BG = "#f1f5f9"
RL_ZEBRA = "#f8fafc"


def _rl_period_label(context):
    df = context.get("date_from")
    dt = context.get("date_to")
    if df and dt:
        return f"{df.strftime('%d/%m/%Y')} \u2013 {dt.strftime('%d/%m/%Y')}"
    if df:
        return f"From {df.strftime('%d/%m/%Y')}"
    if dt:
        return f"Until {dt.strftime('%d/%m/%Y')}"
    return ""


def _rl_wrap(text, max_chars):
    """Naive word wrap into a list of lines (for canvas header/footer)."""
    text = str(text or "").strip()
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _reportlab_branded_page(canvas, doc, branding, context, pagesize):
    from pathlib import Path

    from reportlab.lib import colors
    from reportlab.lib.units import mm

    canvas.saveState()
    width, height = pagesize
    left = doc.leftMargin
    right = width - doc.rightMargin
    navy = colors.HexColor(RL_NAVY)
    muted = colors.HexColor(RL_MUTED)
    header_top = height - 11 * mm

    # ---- Brand block (left) ----
    logo_path = branding.get("logo_path")
    text_x = left
    if logo_path and Path(logo_path).is_file():
        try:
            canvas.drawImage(
                logo_path,
                left,
                header_top - 15 * mm,
                width=15 * mm,
                height=15 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
            text_x = left + 19 * mm
        except Exception:
            pass

    canvas.setFont("Helvetica-Bold", 15)
    canvas.setFillColor(navy)
    canvas.drawString(text_x, header_top - 4 * mm, str(branding.get("name") or "Company")[:34])

    canvas.setFillColor(muted)
    y = header_top - 9 * mm
    addr_lines = _rl_wrap(branding.get("address"), 52)[:2]
    contact_lines = addr_lines + [
        s for s in (branding.get("phone"), branding.get("email")) if s
    ]
    canvas.setFont("Helvetica", 7.5)
    for line in contact_lines[:4]:
        canvas.drawString(text_x, y, str(line)[:62])
        y -= 3.6 * mm

    # ---- Title block (right) ----
    canvas.setFillColor(navy)
    canvas.setFont("Helvetica-Bold", 17)
    canvas.drawRightString(right, header_top - 4 * mm, str(context.get("pdf_report_title") or "").upper()[:34])

    ry = header_top - 10 * mm
    period = "" if context.get("pdf_hide_period") else _rl_period_label(context)
    if period:
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(muted)
        canvas.drawRightString(right, ry, f"Period: {period}")
        ry -= 5 * mm

    account_name = context.get("pdf_account_name")
    if account_name:
        acct_id = context.get("pdf_account_id")
        label = f"{account_name} ({acct_id})" if acct_id else str(account_name)
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(muted)
        canvas.drawRightString(right, ry, "Account:")
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.setFillColor(navy)
        canvas.drawRightString(right, ry - 4.6 * mm, label[:46])

    # ---- Header divider ----
    canvas.setStrokeColor(navy)
    canvas.setLineWidth(1.6)
    canvas.line(left, height - 32 * mm, right, height - 32 * mm)

    # ---- Footer ----
    fy = 16 * mm
    canvas.setStrokeColor(colors.HexColor("#d8dfe8"))
    canvas.setLineWidth(0.7)
    canvas.line(left, fy + 7 * mm, right, fy + 7 * mm)

    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.setFillColor(navy)
    canvas.drawString(left, fy + 3 * mm, str(branding.get("footer_text") or branding.get("name") or "")[:60])

    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(muted)
    addr_one = _rl_wrap(branding.get("address"), 80)
    if addr_one:
        canvas.drawString(left, fy - 0.5 * mm, addr_one[0][:90])
    contact = "  |  ".join(s for s in (branding.get("email"), branding.get("phone")) if s)
    if contact:
        canvas.drawString(left, fy - 4 * mm, contact[:90])

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(muted)
    canvas.drawRightString(right, fy + 3 * mm, f"Page {canvas.getPageNumber()}")
    canvas.drawRightString(
        right, fy - 1 * mm, f"Printed on: {_format_cell(context.get('pdf_generated_on', date.today()))}"
    )
    canvas.restoreState()


def _rl_account_card(context, avail):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    name = context.get("pdf_account_name")
    if not name:
        return None
    acct_id = context.get("pdf_account_id")
    label_st = ParagraphStyle("acctLabel", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor(RL_MUTED), leading=10)
    value_st = ParagraphStyle("acctValue", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor(RL_NAVY), leading=15)

    def cell(label, value):
        return [Paragraph(label, label_st), Paragraph(str(value or "\u2014"), value_st)]

    cols = [cell("Account Name", name)]
    if acct_id:
        cols.append(cell("Account ID", acct_id))
    if len(cols) == 1:
        cols.append([Paragraph("", label_st)])
    data = [[cols[0], cols[1]]]
    t = Table(data, colWidths=[avail / 2.0, avail / 2.0])
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fcfdff")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe2ec")),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if acct_id:
        style.append(("LINEAFTER", (0, 0), (0, 0), 0.6, colors.HexColor("#cbd5e1")))
    t.setStyle(TableStyle(style))
    return t


def _rl_stat_cards(context, avail):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    cards = context.get("pdf_stat_cards") or []
    if not cards:
        return None
    palette = {
        "debit": (RL_DEBIT_BG, RL_DEBIT),
        "credit": (RL_CREDIT_BG, RL_CREDIT),
        "balance": (RL_BALANCE_BG, RL_NAVY),
        "neutral": (RL_NEUTRAL_BG, RL_MUTED),
    }
    value_st = ParagraphStyle("statVal", fontName="Helvetica-Bold", fontSize=14, textColor=colors.HexColor(RL_NAVY), leading=17)
    gap = 8
    n = len(cards)
    card_w = (avail - gap * (n - 1)) / n
    inner = []
    styles_per = []
    for idx, card in enumerate(cards):
        kind = card.get("kind") or "neutral"
        bg, fg = palette.get(kind, palette["neutral"])
        label_st = ParagraphStyle(
            f"statLbl{idx}", fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.HexColor(fg), leading=11
        )
        cell = [Paragraph(str(card.get("label", "")).upper(), label_st), Paragraph(str(card.get("value", "")), value_st)]
        mini = Table([[cell]], colWidths=[card_w])
        mini.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("TOPPADDING", (0, 0), (-1, -1), 13),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        inner.append(mini)
        if idx:
            styles_per.append(("LEFTPADDING", (idx, 0), (idx, 0), gap))
    outer = Table([inner], colWidths=[card_w + (gap if i else 0) for i in range(n)])
    base = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    outer.setStyle(TableStyle(base + styles_per))
    return outer


def _rl_section_title(context):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    title = context.get("pdf_section_title")
    if not title:
        return []
    out = [
        Paragraph(
            str(title).upper(),
            ParagraphStyle(
                "secTitle", fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor(RL_NAVY), leading=14
            ),
        )
    ]
    subtitle = context.get("pdf_section_subtitle")
    if subtitle:
        out.append(
            Paragraph(
                str(subtitle),
                ParagraphStyle(
                    "secSub", fontName="Helvetica", fontSize=8, textColor=colors.HexColor(RL_MUTED), leading=11
                ),
            )
        )
    return out


def _rl_main_table(context, avail, cell_style):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    headers = context.get("pdf_table_headers") or []
    table_rows = context.get("pdf_table_rows") or []
    numeric = set(context.get("pdf_numeric_column_indexes") or [])
    wrap = set(context.get("pdf_wrap_column_indexes") or [])
    badge_idx = context.get("pdf_badge_column_index", -1)
    col_count = len(headers)

    head_st = ParagraphStyle(
        "thCell", fontName="Helvetica-Bold", fontSize=7.2, textColor=colors.white, leading=9
    )
    head_st_r = ParagraphStyle("thCellR", parent=head_st, alignment=2)
    head_st_c = ParagraphStyle("thCellC", parent=head_st, alignment=1)

    def header_cell(i, text):
        if i in numeric:
            st = head_st_r
        elif i == badge_idx:
            st = head_st_c
        else:
            st = head_st
        return Paragraph(str(text).upper(), st)

    pill_styles = {
        "DEBIT": ParagraphStyle("pillD", fontName="Helvetica-Bold", fontSize=7.6, alignment=1, textColor=colors.HexColor(RL_DEBIT)),
        "CREDIT": ParagraphStyle("pillC", fontName="Helvetica-Bold", fontSize=7.6, alignment=1, textColor=colors.HexColor(RL_CREDIT)),
    }
    neutral_pill = ParagraphStyle("pillN", fontName="Helvetica-Bold", fontSize=7.6, alignment=1, textColor=colors.HexColor(RL_NAVY))
    num_style = ParagraphStyle("numCell", parent=cell_style, alignment=2)

    def body_cell(i, cell):
        if i == badge_idx and cell:
            return Paragraph(str(cell).upper(), pill_styles.get(str(cell).upper(), neutral_pill))
        if i in numeric:
            return Paragraph(str(cell), num_style)
        return _reportlab_cell_paragraph(cell, cell_style)

    data = [[header_cell(i, h) for i, h in enumerate(headers)]]
    row_kinds = context.get("pdf_table_row_kinds") or []
    extra_style = []
    for r_idx, row in enumerate(table_rows):
        cells = _pdf_row_cells(row)
        kind = _pdf_row_kind(row, r_idx, row_kinds)
        data.append([body_cell(i, c) for i, c in enumerate(cells)])
        if kind == "summary":
            style_row = r_idx + 1
            extra_style.append(("BACKGROUND", (0, style_row), (-1, style_row), colors.HexColor("#f8fafc")))
            extra_style.append(("FONTNAME", (0, style_row), (-1, style_row), "Helvetica-Bold"))
    if context.get("pdf_footer_row"):
        fr = context["pdf_footer_row"]
        footer_idx = len(data)
        data.append([Paragraph(str(c), num_style if i in numeric else cell_style) for i, c in enumerate(fr)])
        extra_style.append(("BACKGROUND", (0, footer_idx), (-1, footer_idx), colors.HexColor(RL_BALANCE_BG)))
        extra_style.append(("FONTNAME", (0, footer_idx), (-1, footer_idx), "Helvetica-Bold"))
        extra_style.append(("LINEABOVE", (0, footer_idx), (-1, footer_idx), 0.8, colors.HexColor(RL_NAVY)))

    width_pcts = context.get("pdf_column_widths")
    if width_pcts and len(width_pcts) == col_count:
        col_widths = [avail * (float(w.strip("%")) / 100.0) for w in width_pcts]
    else:
        col_widths = [avail / max(col_count, 1)] * col_count

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(RL_TABLE_HEAD)),
        ("FONTSIZE", (0, 0), (-1, -1), 8.4),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, colors.HexColor("#eef1f6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(RL_ZEBRA)]),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
    ]
    # tint the Type/badge cells
    if isinstance(badge_idx, int) and 0 <= badge_idx < col_count:
        for r, row in enumerate(table_rows, start=1):
            cells = _pdf_row_cells(row)
            val = str(cells[badge_idx]).upper() if badge_idx < len(cells) else ""
            if val == "DEBIT":
                style.append(("BACKGROUND", (badge_idx, r), (badge_idx, r), colors.HexColor(RL_DEBIT_BG)))
            elif val == "CREDIT":
                style.append(("BACKGROUND", (badge_idx, r), (badge_idx, r), colors.HexColor(RL_CREDIT_BG)))
    style.extend(extra_style)
    t.setStyle(TableStyle(style))
    return t


def _rl_totals(context, avail):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    totals = context.get("pdf_totals")
    if not totals:
        return None
    closing_last = context.get("pdf_totals_closing_last")
    label_st = ParagraphStyle("totLbl", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.HexColor(RL_MUTED), leading=12)
    val_st = ParagraphStyle("totVal", fontName="Helvetica-Bold", fontSize=9.5, alignment=2, textColor=colors.HexColor(RL_NAVY), leading=12)
    closing_lbl = ParagraphStyle("clLbl", parent=label_st, fontSize=10.5, textColor=colors.HexColor(RL_NAVY))
    closing_val = ParagraphStyle("clVal", parent=val_st, fontSize=10.5)

    data = []
    n = len(totals)
    for i, (label, value) in enumerate(totals):
        is_closing = closing_last and i == n - 1
        data.append(
            [
                Paragraph(str(label), closing_lbl if is_closing else label_st),
                Paragraph(str(value), closing_val if is_closing else val_st),
            ]
        )
    t = Table(data, colWidths=[avail * 0.72, avail * 0.28])
    style = [
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor(RL_LINE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if closing_last and n:
        style.append(("BACKGROUND", (0, n - 1), (-1, n - 1), colors.HexColor(RL_BALANCE_BG)))
        style.append(("LINEBELOW", (0, n - 1), (-1, n - 1), 0, colors.white))
    t.setStyle(TableStyle(style))
    return t


def _reportlab_branded_pdf(filename, context):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    branding = context.get("company") or get_company_branding()
    buffer = BytesIO()
    table_rows = context.get("pdf_table_rows") or []
    headers = context.get("pdf_table_headers") or []
    col_count = len(headers) if headers else (len(table_rows[0]) if table_rows else 1)
    use_landscape = col_count > 8
    pagesize = landscape(A4) if use_landscape else A4
    cell_style = ParagraphStyle(
        "PdfTableCell",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=11,
        textColor=colors.HexColor(RL_INK),
        wordWrap="CJK",
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=37 * mm,
        bottomMargin=26 * mm,
        title=str(context.get("pdf_report_title") or filename),
    )
    avail = pagesize[0] - doc.leftMargin - doc.rightMargin
    styles = getSampleStyleSheet()
    story = []

    acct = _rl_account_card(context, avail)
    if acct is not None:
        story.append(acct)
        story.append(Spacer(1, 14))

    stat = _rl_stat_cards(context, avail)
    if stat is not None:
        story.append(stat)
        story.append(Spacer(1, 16))

    section = _rl_section_title(context)
    if section:
        story.extend(section)
        story.append(Spacer(1, 8))

    if headers and table_rows:
        story.append(_rl_main_table(context, avail, cell_style))
        story.append(Spacer(1, 14))
    elif context.get("pdf_empty_message"):
        empty_st = ParagraphStyle(
            "emptyMsg", parent=styles["Normal"], alignment=1, fontSize=9.5, textColor=colors.HexColor(RL_MUTED)
        )
        story.append(Spacer(1, 10))
        story.append(Paragraph(str(context["pdf_empty_message"]), empty_st))

    totals = _rl_totals(context, avail)
    if totals is not None:
        story.append(totals)
    elif context.get("pdf_summary_cards") and not (headers and table_rows):
        data = [[str(a), str(b)] for a, b in context["pdf_summary_cards"]]
        t = Table(data, colWidths=[avail * 0.6, avail * 0.4])
        t.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(RL_LINE)),
                    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(RL_MUTED)),
                    ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(RL_NAVY)),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(t)

    if not story:
        story.append(Paragraph("Document content unavailable.", styles["Normal"]))

    def on_page(canvas, doc_obj):
        _reportlab_branded_page(canvas, doc_obj, branding, context, pagesize)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _reportlab_table_pdf(filename, context):
    return _reportlab_branded_pdf(filename, context)


def render_or_pdf(request, template_name, context, filename):
    merged = build_pdf_context(request, filename, context)
    export_fmt = (request.GET.get("format") or "").lower()
    if export_fmt == "xlsx":
        from accounts_core.export_utils import build_xlsx_response

        headers = merged.get("pdf_table_headers") or []
        rows = [_pdf_row_cells(r) for r in (merged.get("pdf_table_rows") or [])]
        xlsx_name = filename.replace(".pdf", "") if filename.endswith(".pdf") else filename
        return build_xlsx_response(xlsx_name, headers, rows)
    if export_fmt != "pdf":
        merged["is_pdf"] = False
        return render(request, template_name, merged)

    merged["is_pdf"] = True

    is_document_pdf = merged.get("payment") and not merged.get("pdf_table_rows")
    use_table_template = not is_document_pdf and (
        merged.get("pdf_table_rows")
        or merged.get("pdf_summary_cards")
        or merged.get("pdf_empty_message")
    )

    if use_table_template:
        try:
            from weasyprint import HTML

            html = render_to_string("pdf/table_report.html", context=merged, request=request)
            pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception:
            return _reportlab_branded_pdf(filename, merged)

    try:
        from weasyprint import HTML

        html = render_to_string(template_name, context=merged, request=request)
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except Exception:
        return _reportlab_branded_pdf(filename, merged)


def pdf_download_query(request):
    params = request.GET.copy()
    params["format"] = "pdf"
    return params.urlencode()
