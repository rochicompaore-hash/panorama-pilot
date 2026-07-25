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
from app.services.recipes.commercial_perimeter import (
    compute_perimeter,
    PerimeterInput,
    PerimeterResult,
    RECIPE_CODE as COMMERCIAL_PERIMETER_CODE,
)
from app.services.recipes.glass_engine import (
    resolve_glass_recipe, compute_glass_dimensions, seed_factory_glass_recipes,
)

# Dispatch table: pricing_mode → (engine, display_dict fn)
PRICING_MODES = {
    "commercial_perimeter": COMMERCIAL_PERIMETER_CODE,
    "technical_cut_list": FINESTRA_1A_CODE,
}
DEFAULT_PRICING_MODE = "commercial_perimeter"

__all__ = [
    "compute_finestra_1a", "FinestraAResult", "FinestraAInput",
    "FINESTRA_1A_CODE",
    "compute_perimeter", "PerimeterInput", "PerimeterResult",
    "COMMERCIAL_PERIMETER_CODE",
    "resolve_glass_recipe", "compute_glass_dimensions", "seed_factory_glass_recipes",
    "PRICING_MODES", "DEFAULT_PRICING_MODE",
]
