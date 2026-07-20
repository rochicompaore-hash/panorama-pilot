"""Product recipes — deterministic BOM + costing engines per product type.

Every recipe:
- Reads inputs (dimensions, colour, kit, other components) — never assumes zero
- Validates geometry — raises structured errors on invalid dimensions
- Produces a cut-list (millimetri) and quantities
- Converts to linear meters / square meters
- Applies unit prices (never €0 silently)
- Aggregates costs into materials / labour / production / sale price
- Returns a signed snapshot (canonical JSON hash)

Recipes never touch the database directly: the router loads prices and passes them in.
"""
from app.services.recipes.finestra_1a import (
    compute_finestra_1a,
    FinestraAResult,
    FinestraAInput,
    RECIPE_CODE as FINESTRA_1A_CODE,
)

__all__ = [
    "compute_finestra_1a", "FinestraAResult", "FinestraAInput",
    "FINESTRA_1A_CODE",
]
