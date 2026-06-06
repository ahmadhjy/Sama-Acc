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

STATEMENT_HEADERS = ["Date", "Reference", "Description", "Debit", "Credit", "Balance"]
STATEMENT_HEADERS_WITH_PARTY = [
    "Account",
    "Date",
    "Reference",
    "Description",
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


def _statement_description(r):
    desc = (r.get("description") or "").strip()
    typ = (r.get("type") or "").strip()
    if desc and typ and typ not in desc:
        return f"{typ} — {desc}"
    return desc or typ or ""


def _flatten_statement_row(r):
    return [
        _format_cell(r.get("date")),
        _format_cell(r.get("ref")),
        _statement_description(r),
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
        context["pdf_numeric_column_indexes"] = [4, 5, 6]
        context["pdf_ref_column_index"] = 2
        context["pdf_description_column_index"] = 3
    else:
        context["pdf_table_headers"] = STATEMENT_HEADERS
        context["pdf_numeric_column_indexes"] = [3, 4, 5]
        context["pdf_ref_column_index"] = 1
        context["pdf_description_column_index"] = 2
    context["pdf_totals"] = [
        ("Total Debit", _format_cell(total_dr)),
        ("Total Credit", _format_cell(total_cr)),
        ("Closing Balance", _format_cell(closing)),
    ]
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
    merged.setdefault("pdf_hide_subtitle_in_body", False)
    if is_pdf or is_xlsx:
        prepare_pdf_export(merged)
    return merged


def _reportlab_cell_paragraph(text, style):
    from xml.sax.saxutils import escape

    from reportlab.platypus import Paragraph

    safe = escape(str(text or ""))
    return Paragraph(safe, style)


def _reportlab_branded_page(canvas, doc, branding, context, pagesize):
    from pathlib import Path

    from reportlab.lib import colors
    from reportlab.lib.units import mm

    canvas.saveState()
    width, height = pagesize
    left = doc.leftMargin
    right = width - doc.rightMargin
    header_top = height - 8 * mm

    logo_path = branding.get("logo_path")
    text_x = left
    if logo_path and Path(logo_path).is_file():
        try:
            canvas.drawImage(
                logo_path,
                left,
                header_top - 13 * mm,
                width=13 * mm,
                height=13 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
            text_x = left + 18 * mm
        except Exception:
            pass

    canvas.setFont("Helvetica-Bold", 9.5)
    canvas.setFillColor(colors.HexColor("#0f2744"))
    company_name = str(branding.get("name") or "Company")
    canvas.drawString(text_x, header_top - 4 * mm, company_name[:60])

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#475569"))
    y = header_top - 8 * mm
    for line in (branding.get("address"), branding.get("phone"), branding.get("email")):
        if line:
            canvas.drawString(text_x, y, str(line)[:95])
            y -= 3.2 * mm

    title = str(context.get("pdf_report_title") or "")
    canvas.setFont("Helvetica-Bold", 11)
    canvas.setFillColor(colors.HexColor("#0f2744"))
    canvas.drawRightString(right, header_top - 4 * mm, title[:50])
    subtitle = context.get("pdf_report_subtitle")
    if subtitle:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawRightString(right, header_top - 8.5 * mm, str(subtitle)[:60])

    canvas.setStrokeColor(colors.HexColor("#0f2744"))
    canvas.setLineWidth(1.2)
    rule_y = header_top - 18 * mm
    canvas.line(left, rule_y, right, rule_y)

    footer_y = 9 * mm
    canvas.setFont("Helvetica", 6.8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    footer_brand = branding.get("footer_text") or branding.get("name") or ""
    if footer_brand:
        canvas.drawString(left, footer_y + 3 * mm, str(footer_brand)[:90])
    contact_bits = [b for b in (branding.get("address"), branding.get("email"), branding.get("phone")) if b]
    if contact_bits:
        canvas.drawString(left, footer_y, " · ".join(str(b) for b in contact_bits)[:110])
    canvas.drawRightString(
        right,
        footer_y + 1.5 * mm,
        f"Page {canvas.getPageNumber()}  ·  Printed {_format_cell(context.get('pdf_generated_on', date.today()))}",
    )
    canvas.restoreState()


def _reportlab_invoice_story(context, styles, cell_style):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    invoice = context["invoice"]
    lines = context.get("lines") or []
    show_costs = context.get("show_costs")
    story = []
    meta_style = styles["Normal"]
    story.append(
        Paragraph(
            f"<b>Invoice:</b> {invoice.invoice_no} &nbsp;|&nbsp; "
            f"<b>Client:</b> {invoice.client.name_en} &nbsp;|&nbsp; "
            f"<b>Issue:</b> {_format_cell(invoice.issue_date)} &nbsp;|&nbsp; "
            f"<b>Due:</b> {_format_cell(invoice.due_date)}",
            meta_style,
        )
    )
    if invoice.package_type:
        story.append(Paragraph(f"<b>Type of service:</b> {invoice.get_package_type_display()}", meta_style))
    story.append(Spacer(1, 6))

    headers = ["Date", "Service", "Destination"]
    if show_costs:
        headers.append("Supplier")
    headers.extend(["Qty", "Sell"])
    if show_costs:
        headers.extend(["Cost", "Cost USD"])
    headers.append("Description")

    table_data = [headers]
    for line in lines:
        row = [
            _format_cell(line.effective_service_date),
            line.service_type.name if line.service_type_id else "—",
            line.destination.name if line.destination_id else "—",
        ]
        if show_costs:
            row.append(line.supplier.name if line.supplier_id else "—")
        row.extend([_format_cell(line.qty), _format_cell(line.sell_price)])
        if show_costs:
            row.extend([_format_cell(line.cost_price), _format_cell(line.cost_price_usd)])
        row.append(line.statement_description or "")
        table_data.append(row)

    footer_colspan = len(headers) - 1
    total_row = [""] * footer_colspan + [f"Grand total: {invoice.grand_total} {invoice.currency}"]
    table_data.append(total_row)
    if show_costs:
        table_data.append([""] * footer_colspan + [f"Total cost (USD): {invoice.total_line_cost_usd}"])
        table_data.append([""] * footer_colspan + [f"Profit (USD): {invoice.profit_amount}"])

    from reportlab.platypus import Spacer, Table, TableStyle

    t = Table(table_data, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5cdd6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t)
    return story


def _reportlab_payment_story(context, styles):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table, TableStyle

    payment = context["payment"]
    party = _party_label(payment)
    rows = [
        ["Receipt number", payment.receipt_no],
        ["Reference", payment.reference or "—"],
        ["Party", party],
        ["Date", _format_cell(payment.date)],
        ["Money account", payment.money_account.name],
        ["Direction", payment.get_direction_display() or payment.direction],
        ["Status", payment.status],
        ["Amount", f"{payment.amount} {payment.currency}"],
        ["Note", payment.note or "—"],
    ]
    t = Table(rows, colWidths=[45 * mm, 120 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return [t]


def _reportlab_branded_pdf(filename, context):
    from io import BytesIO
    from pathlib import Path

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
    use_landscape = col_count > 6
    pagesize = landscape(A4) if use_landscape else A4
    numeric = set(context.get("pdf_numeric_column_indexes") or [])
    wrap = set(context.get("pdf_wrap_column_indexes") or [])
    cell_style = ParagraphStyle(
        "PdfTableCell",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=8,
        leading=10,
        wordWrap="CJK",
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=11 * mm,
        rightMargin=11 * mm,
        topMargin=30 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    if context.get("invoice"):
        story = _reportlab_invoice_story(context, styles, cell_style)
    elif context.get("payment"):
        story = _reportlab_payment_story(context, styles)
    elif headers and table_rows:
        def _rl_row(cells, header_row=False):
            out = []
            for i, cell in enumerate(cells):
                if header_row or (i in numeric and i not in wrap):
                    out.append(str(cell))
                else:
                    out.append(_reportlab_cell_paragraph(cell, cell_style))
            return out

        table_data = [_rl_row(headers, header_row=True)] + [_rl_row(row) for row in table_rows]
        if context.get("pdf_footer_row"):
            table_data.append(_rl_row(context["pdf_footer_row"]))
        avail = pagesize[0] - doc.leftMargin - doc.rightMargin
        width_pcts = context.get("pdf_column_widths")
        if width_pcts and len(width_pcts) == col_count:
            col_widths = [avail * (float(w.strip("%")) / 100.0) for w in width_pcts]
        else:
            col_widths = [avail / max(col_count, 1)] * col_count
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0e1f3d")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5cdd6")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t)
        if context.get("pdf_totals"):
            totals_data = [[label, value] for label, value in context["pdf_totals"]]
            story.append(Spacer(1, 6))
            story.append(Table(totals_data, colWidths=[50 * mm, 40 * mm]))
    elif context.get("pdf_summary_cards"):
        table_data = [["Metric", "Value"]] + [[str(a), str(b)] for a, b in context["pdf_summary_cards"]]
        t = Table(table_data, colWidths=[90 * mm, 80 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        story.append(t)
    elif context.get("pdf_empty_message"):
        story.append(Paragraph(context["pdf_empty_message"], styles["Normal"]))
    else:
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
        rows = merged.get("pdf_table_rows") or []
        xlsx_name = filename.replace(".pdf", "") if filename.endswith(".pdf") else filename
        return build_xlsx_response(xlsx_name, headers, rows)
    if export_fmt != "pdf":
        merged["is_pdf"] = False
        return render(request, template_name, merged)

    merged["is_pdf"] = True

    is_document_pdf = merged.get("invoice") or merged.get("payment")
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
