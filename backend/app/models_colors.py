"""Anagrafica Colori PVC + Colori Zanzariere (F1 Real Catalog V1)."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models import BaseDoc


class ProductColor(BaseDoc):
    """Anagrafica colori PVC (unica, multi-dominio di prezzo).

    Regole vincolanti F1:
      - `pvc_color_category` ∈ MASS_COLOR / STANDARD / SPECIAL / NEEDS_PO_MAPPING
      - `cassonetti_price_family` ∈ BIANCO_MASSA / STANDARD / NON_STANDARD / NEEDS_PO_MAPPING
      - I due domini sono indipendenti (§1 direttiva mapping).
      - `finish_type` è metadato descrittivo, NON deriva le famiglie prezzo.
      - `visual_hex` opzionale (usato da F3 renderer SVG). Se assente il renderer
        mostra "Rappresentazione colore indicativa".
    """
    code: str                              # 003, 100, 154, ...
    name: str                              # BIANCO MASSA
    ral_reference: Optional[str] = None    # "9016"
    pvc_color_category: str = "NEEDS_PO_MAPPING"
    cassonetti_price_family: str = "NEEDS_PO_MAPPING"
    finish_type: Optional[str] = None      # descriptive: MASS / FOIL / WOOD_EFFECT / METAL / MARBLE
    mass_color: bool = False
    foil: bool = False
    available_internal: bool = True
    available_external: bool = True
    visual_hex: Optional[str] = None
    visual_asset: Optional[str] = None
    display_order: int = 0
    active: bool = True
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    notes: Optional[str] = None


class ProductColorCreate(BaseModel):
    code: str
    name: str
    ral_reference: Optional[str] = None
    pvc_color_category: str = "NEEDS_PO_MAPPING"
    cassonetti_price_family: str = "NEEDS_PO_MAPPING"
    finish_type: Optional[str] = None
    mass_color: bool = False
    foil: bool = False
    available_internal: bool = True
    available_external: bool = True
    visual_hex: Optional[str] = None
    display_order: int = 0
    active: bool = True


class ProductColorUpdate(BaseModel):
    name: Optional[str] = None
    ral_reference: Optional[str] = None
    pvc_color_category: Optional[str] = None
    cassonetti_price_family: Optional[str] = None
    finish_type: Optional[str] = None
    visual_hex: Optional[str] = None
    display_order: Optional[int] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class ZanzarieraColor(BaseDoc):
    """Anagrafica colori zanzariere (tassonomia SEPARATA — §7 direttiva mapping).

    price_category ∈ BASE / WOOD_EFFECT / MARBLE / SPECIAL / NEEDS_PO_MAPPING.
    """
    code: str
    name: str
    price_category: str = "NEEDS_PO_MAPPING"
    applies_to_models: List[str] = Field(default_factory=list)  # SWITCH_5, SKAT, ...
    visual_hex: Optional[str] = None
    display_order: int = 0
    active: bool = True
