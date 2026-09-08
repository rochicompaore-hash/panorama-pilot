| product_id | product_name | category | pricing_model | cost_source | sale_rule | multiplier | minimum | color_pricing | installation_resolver | internal_cost_available | sale_price_available | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 899ec211-e375-4215-b8d6-0c1423a986f8 | TEST Prodotto Lineare 25€/ml | ACCESSORI | LINEAR_METER | NONE | LINEAR_METER unit_sale/fixed | None | None | - | None | False | True | PASS_TEST_FIXTURE_ONLY (no cost — escluso dal catalogo commerciale) |
| 061c35f0-0da7-44bd-8bae-ab7b3453830d | TEST Accessorio 50€/pz | ACCESSORI | PER_ITEM | NONE | PER_ITEM unit_sale/fixed | None | None | - | None | False | True | PASS_TEST_FIXTURE_ONLY (no cost — escluso dal catalogo commerciale) |
| dc5ac292-692f-4aa9-8065-83bd7664928c | Cassonetto — Listino Ufficiale 2026 | CASSONETTI | GRID | grid cell internal (workbook) | grid cell sale (workbook lookup) | None | None | PVC | INSTALL_ROLLER_BOX_SINGLE | True | True | PASS |
| 8e1cafd0-9707-47c7-8939-b97c9a404021 | ProEvolution | FINESTRE | FORMULA_TECHNICAL | technical BOM (pricing_v3) | technical_cost × package multiplier | 3.0 | None | - | INSTALL_WINDOW_1_2_SASH | True | True | PASS |
| e5e97bea-d28c-4ea0-878a-80eb2c208db5 | Persiana in alluminio (RAL / Effetto legno / Speciali) | PERSIANE_SCURI | AREA_PURCHASE_MULTIPLIER | purchase €/m² per color category | purchase × multiplier | 2.5 | 1.3 | INTERNAL_MAP | INSTALL_SHUTTER_1_2_SASH | True | True | PASS |
| d96b0e38-e12c-4782-9d76-87d28e25c2a5 | TEST Servizio Fisso 120€ | SERVIZI | FIXED_PRICE | NONE | FIXED_PRICE unit_sale/fixed | None | None | - | None | False | True | PASS_TEST_FIXTURE_ONLY (no cost — escluso dal catalogo commerciale) |
| 1ddf23e0-cc3e-444f-91af-cdfd5e270bc2 | Tapparella PVC (3 varianti — ×3) | TAPPARELLE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 1.5 | INTERNAL_MAP | INSTALL_ROLLER_KIT | True | True | PASS |
| 72424c0e-507e-4c2e-aa96-77a6af62ab4b | Zanzariera Skat | ZANZARIERE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 1.5 | ZANZARIERE | INSTALL_MOSQUITO | True | True | PASS |
| d94ed44a-7e1e-4629-84f1-744b79e20fd9 | Zanzariera Switch 5 | ZANZARIERE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 2.0 | ZANZARIERE | INSTALL_MOSQUITO | True | True | PASS |
| 9c33b8cc-8710-4802-8cab-a2f42cc8b787 | TEST AREA 100€/m² min 1.50 | ZANZARIERE | AREA | NONE | AREA unit_sale/fixed | None | 1.5 | - | INSTALL_MOSQUITO | False | True | PASS_TEST_FIXTURE_ONLY (no cost — escluso dal catalogo commerciale) |
| 53819f84-b2ee-4df1-83c5-4f67f340c761 | Zanzariera Unikcat | ZANZARIERE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 1.5 | ZANZARIERE | INSTALL_MOSQUITO | True | True | PASS |
| cc20c036-8205-41a0-a2d6-c85d4aaf4c7b | Zanzariera Uniklat | ZANZARIERE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 2.0 | ZANZARIERE | INSTALL_MOSQUITO | True | True | PASS |
| c9b14d1f-553e-4d7d-8237-88e7bc9fb6a8 | Zanzariera Unikver | ZANZARIERE | AREA | purchase €/m² per color category | purchase × multiplier | 3.0 | 1.5 | ZANZARIERE | INSTALL_MOSQUITO | True | True | PASS |

TOTAL=13 PASS=13 FAIL=0
