"""Company branding for PDF exports (DB singleton with settings fallback)."""

from pathlib import Path

from django.conf import settings
from django.templatetags.static import static


def get_company_branding(request=None):
    from accounts_core.models import CompanyBranding

    row = CompanyBranding.load()
    name = row.name or getattr(settings, "COMPANY_LEGAL_NAME", "Sama Tours")
    address = row.address or getattr(settings, "COMPANY_ADDRESS", "")
    phone = row.phone or getattr(settings, "COMPANY_PHONE", "")
    email = row.email or getattr(settings, "COMPANY_EMAIL", "")
    financial_account_number = row.financial_account_number or getattr(
        settings, "COMPANY_FINANCIAL_ACCOUNT", ""
    )
    footer_text = row.footer_text or getattr(settings, "COMPANY_FOOTER_TEXT", "")
    tagline = getattr(settings, "COMPANY_TAGLINE", "")
    default_currency = row.default_currency or getattr(settings, "COMPANY_DEFAULT_CURRENCY", "USD")

    logo_url = None
    logo_path = None
    if row.logo:
        try:
            path = Path(row.logo.path)
            if path.is_file():
                logo_path = str(path)
        except (ValueError, OSError):
            pass
        if not logo_path:
            url = row.logo.url
            logo_url = request.build_absolute_uri(url) if request else url
    if not logo_path:
        static_logo = settings.BASE_DIR / "static" / "media" / "logo.png"
        if static_logo.is_file():
            logo_path = str(static_logo)

    if logo_path and Path(logo_path).is_file():
        logo_url = Path(logo_path).as_uri()
    elif not logo_url:
        rel = static("media/logo.png")
        logo_url = request.build_absolute_uri(rel) if request else rel

    return {
        "name": name,
        "address": address,
        "phone": phone,
        "email": email,
        "financial_account_number": financial_account_number,
        "footer_text": footer_text,
        "tagline": tagline,
        "default_currency": default_currency,
        "logo_url": logo_url,
        "logo_path": logo_path,
        "has_uploaded_logo": bool(row.logo),
    }
