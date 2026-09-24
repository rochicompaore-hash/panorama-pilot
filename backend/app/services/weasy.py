"""Lazy WeasyPrint loader: evita import a boot (richiede libgobject/pango di sistema)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PdfEngineUnavailable(RuntimeError):
    pass


def html_to_pdf(html_str: str, base_url: str, stylesheets=None) -> bytes:
    try:
        from weasyprint import HTML  # noqa: WPS433
    except Exception as e:  # OSError su librerie native mancanti
        logger.error("WeasyPrint non disponibile: %s", e)
        raise PdfEngineUnavailable("PDF_ENGINE_UNAVAILABLE: librerie native (pango/gobject) mancanti nell'ambiente") from e
    kwargs = {"stylesheets": stylesheets} if stylesheets else {}
    return HTML(string=html_str, base_url=base_url).write_pdf(**kwargs)
