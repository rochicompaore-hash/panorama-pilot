"""AUDIT v1 · Regression tests for fixes BUG-01/02/03/04/06/15.

Non modifica lo schema DB né i dati; usa mock in-memory dove possibile.
"""
from __future__ import annotations
import asyncio
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# ================================================================
# BUG-06 — glass_engine ROUND_HALF_UP (unit test puro, no DB)
# ================================================================
def test_bug06_glass_engine_no_silent_truncation():
    """Verifica che compute_glass_dimensions arrotondi correttamente 526.5 → 527."""
    from app.services.recipes.glass_engine import compute_glass_dimensions

    # 2 ante: L=1400, wr=347, sf=2 → (1053)/2 = 526.5 → deve dare 527, non 526
    recipe = {
        "formula_type": "structured",
        "structured": {
            "width_reduction_mm": 347, "height_reduction_mm": 206,
            "split_factor": 2, "quantity": 2,
        },
    }
    gw, gh, qty = compute_glass_dimensions(recipe, L_mm=1400, H_mm=1500)
    assert gw == 527, f"Attesa larghezza 527 (era 526 con troncamento), ottenuto {gw}"
    assert gh == 1294
    assert qty == 2

    # 1 anta: L=900, wr=206, sf=1 → (694)/1 = 694 → 694 (nessun arrotondamento)
    recipe2 = {
        "formula_type": "structured",
        "structured": {
            "width_reduction_mm": 206, "height_reduction_mm": 206,
            "split_factor": 1, "quantity": 1,
        },
    }
    gw2, gh2, qty2 = compute_glass_dimensions(recipe2, L_mm=900, H_mm=1500)
    assert gw2 == 694 and gh2 == 1294 and qty2 == 1


def test_bug06_glass_engine_handles_missing_split_factor():
    """split_factor=None / mancante → deve fallback a 1 senza crash (comportamento coerente)."""
    from app.services.recipes.glass_engine import compute_glass_dimensions
    recipe = {"formula_type": "structured", "structured": {
        "width_reduction_mm": 100, "height_reduction_mm": 100,
        "split_factor": None, "quantity": 1,
    }}
    gw, gh, qty = compute_glass_dimensions(recipe, L_mm=1000, H_mm=1500)
    assert gw == 900 and gh == 1400 and qty == 1


# ================================================================
# BUG-03 — get_production_config non inventa glass_price/min_sqm
# ================================================================
def test_bug03_no_silent_defaults_for_glass():
    """DEFAULT_PROD_CFG deve avere None per glass_price/min_sqm (no valori inventati)."""
    from app.services.catalog_service import DEFAULT_PROD_CFG
    assert DEFAULT_PROD_CFG["default_glass_price_per_sqm"] is None, (
        "BUG-03: glass_price non deve avere default silent (era 76.0)"
    )
    assert DEFAULT_PROD_CFG["default_glass_min_sqm"] is None, (
        "BUG-03: glass_min_sqm non deve avere default silent (era 0.50)"
    )
    # Valori tecnici standard OK come default
    assert DEFAULT_PROD_CFG["premium_pvc_surcharge_pct"] == 6.0
    assert DEFAULT_PROD_CFG["default_bar_length_pvc_mm"] == 6500


# ================================================================
# BUG-01 — quotes.py: sent guard controlla lines.pricing_snapshot
# ================================================================
def test_bug01_sent_guard_reads_from_lines_not_opening_products():
    """Verifica che il codice di quotes.py:change_status non legga più db.opening_products."""
    import inspect
    from app.routers import quotes as qr
    src = inspect.getsource(qr.change_status)
    # Non deve più esistere query attiva su db.opening_products (il commento fix può menzionarla)
    assert "db.opening_products" not in src, (
        "BUG-01: change_status non deve interrogare db.opening_products (inesistente)"
    )
    # Deve controllare le lines inline
    assert "pricing_snapshot" in src
    assert "QUOTE_HAS_BLOCKING_ERRORS" in src


# ================================================================
# BUG-02 — resolve_component_prices ordering deterministico
# ================================================================
def test_bug02_pricelist_lookup_deterministic_ordering():
    """Verifica che resolve_component_prices ordini per version DESC + updated_at DESC."""
    import inspect
    from app.services import catalog_service as cs
    src = inspect.getsource(cs.resolve_component_prices)
    assert '"version"' in src and "-1" in src, (
        "BUG-02: deve ordinare pricelist per version DESC"
    )
    assert '"updated_at"' in src, (
        "BUG-02: deve ordinare pricelist per updated_at DESC come tie-breaker"
    )


# ================================================================
# BUG-04 — indici presenti sulle hot collections
# ================================================================
def test_bug04_hot_collections_have_tenant_indexes():
    """Verifica che ensure_indexes() crei i nuovi indici per catalog + motore."""
    import inspect
    from app.services import indexes as idx_mod
    src = inspect.getsource(idx_mod.ensure_indexes)
    for expected_name in [
        "ix_ipl_tenant_status_ver",
        "ix_glass_recipes_lookup",
        "ix_color_categories_tenant_code",
        "ix_ccm_tenant_code",
        "ux_production_config_tenant",
        "ix_products_demo_guard",
    ]:
        assert expected_name in src, f"BUG-04: indice atteso {expected_name} non creato"


# ================================================================
# BUG-15 — production_config unique per tenant
# ================================================================
def test_bug15_production_config_unique_index_defined():
    """L'indice unique per production_config è definito in ensure_indexes."""
    import inspect
    from app.services import indexes as idx_mod
    src = inspect.getsource(idx_mod.ensure_indexes)
    assert "production_config" in src
    assert "unique=True" in src
    assert "ux_production_config_tenant" in src
