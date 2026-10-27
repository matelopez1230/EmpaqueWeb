# maintenance/pdf_generator/pdf_utils.py
import base64
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[2] / "static" / "img" / "logo.png"


def logo_base64() -> str | None:
    if not LOGO_PATH.exists():
        return None
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def generar_pdf(html_string: str) -> bytes:
    """WeasyPrint con import diferido (la app arranca sin él)."""
    from weasyprint import HTML
    return HTML(string=html_string).write_pdf()