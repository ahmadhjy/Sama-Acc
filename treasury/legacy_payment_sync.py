"""Keep SupplierLedgerLine PV/RV in sync when imported (SATO26-) payments are edited."""

from __future__ import annotations

from purchases.models import SupplierLedgerLine
from reporting.supplier_statement_rows import LEGACY_DOC_PREFIX
from treasury.models import Payment


def parse_legacy_receipt(receipt_no: str) -> tuple[str, str] | None:
    """
    Parse SATO26-PV-00012 or SATO26-RV-00012[-suffix] → (journal_type, jvno_padded).
    """
    if not receipt_no or not receipt_no.startswith(LEGACY_DOC_PREFIX):
        return None
    parts = receipt_no.split("-")
    if len(parts) < 3:
        return None
    jtype = (parts[1] or "").upper()
    if jtype not in ("PV", "RV"):
        return None
    jvno = parts[2]
    if not jvno:
        return None
    return jtype, jvno


def _jvno_variants(jvno: str) -> list[str]:
    raw = (jvno or "").strip()
    stripped = raw.lstrip("0") or "0"
    return list({raw, stripped, stripped.zfill(5), raw.zfill(5)})


def ledger_lines_for_payment(payment: Payment, *, supplier_ids=None):
    parsed = parse_legacy_receipt(payment.receipt_no or "")
    if not parsed:
        return SupplierLedgerLine.objects.none()
    jtype, jvno = parsed
    qs = SupplierLedgerLine.objects.filter(
        journal_type=jtype,
        legacy_jvno__in=_jvno_variants(jvno),
    )
    if supplier_ids:
        qs = qs.filter(supplier_id__in=[s for s in supplier_ids if s])
    return qs


def _dc_for_payment(payment: Payment) -> str:
    # Money out to supplier → debit AP; money in from supplier → credit AP.
    if payment.direction == Payment.Direction.OUT:
        return SupplierLedgerLine.DC.DEBIT
    return SupplierLedgerLine.DC.CREDIT


def sync_ledger_from_payment(payment: Payment, *, old_supplier_id=None) -> int:
    """
    Update imported supplier ledger PV/RV rows to match the Payment.

    Returns number of ledger rows updated/created/deleted.
    Client SATO26 payments need no ledger sync (client SOA reads Payment directly).
    """
    if not (payment.receipt_no or "").startswith(LEGACY_DOC_PREFIX):
        return 0
    if payment.party_type != Payment.PartyType.SUPPLIER:
        # Imported client payments: SOA already uses Payment; drop any stray PV/RV if party moved off supplier.
        if old_supplier_id:
            return _delete_ledger_qs(ledger_lines_for_payment(payment, supplier_ids=[old_supplier_id]))
        return 0

    if payment.status != Payment.Status.POSTED:
        return remove_ledger_for_payment(payment, old_supplier_id=old_supplier_id)

    supplier_ids = [payment.supplier_id, old_supplier_id]
    lines = list(ledger_lines_for_payment(payment, supplier_ids=supplier_ids))

    # Prefer a single best match: same supplier + closest amount, else first.
    target = None
    if payment.supplier_id:
        same = [ln for ln in lines if ln.supplier_id == payment.supplier_id]
        if same:
            target = min(same, key=lambda ln: abs(ln.amount - payment.amount))
    if target is None and lines:
        target = lines[0]

    # Remove extras / old-supplier duplicates for this JV.
    changed = 0
    for ln in lines:
        if target is not None and ln.pk == target.pk:
            continue
        ln.delete()
        changed += 1

    desc = ""
    if payment.money_account_id:
        desc = payment.money_account.name
    if payment.note:
        desc = (f"{desc} — {payment.note}" if desc else payment.note)[:255]
    if payment.reference and not desc:
        desc = payment.reference[:255]

    if target is None:
        if not payment.supplier_id:
            return changed
        parsed = parse_legacy_receipt(payment.receipt_no)
        if not parsed:
            return changed
        jtype, jvno = parsed
        SupplierLedgerLine.objects.create(
            supplier_id=payment.supplier_id,
            legacy_key=f"SYNC-{payment.receipt_no}",
            journal_type=jtype,
            legacy_jvno=jvno.lstrip("0") or "0",
            legacy_accno="",
            line_seq=0,
            dc=_dc_for_payment(payment),
            line_date=payment.date,
            amount=payment.amount,
            invoice_no="",
            description=desc or payment.receipt_no,
        )
        return changed + 1

    target.supplier_id = payment.supplier_id
    target.line_date = payment.date
    target.amount = payment.amount
    target.dc = _dc_for_payment(payment)
    if desc:
        target.description = desc
    target.save()
    return changed + 1


def _delete_ledger_qs(qs) -> int:
    count = qs.count()
    qs.delete()
    return count


def remove_ledger_for_payment(payment: Payment, *, old_supplier_id=None) -> int:
    """Delete ledger PV/RV rows tied to an imported payment (void/delete)."""
    if not (payment.receipt_no or "").startswith(LEGACY_DOC_PREFIX):
        return 0
    supplier_ids = [payment.supplier_id, old_supplier_id]
    return _delete_ledger_qs(ledger_lines_for_payment(payment, supplier_ids=supplier_ids))
