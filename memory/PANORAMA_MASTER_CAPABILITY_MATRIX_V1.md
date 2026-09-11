# PANORAMA_MASTER_CAPABILITY_MATRIX_V1
**Data:** 11 Set 2026 · **Modalità:** AUDIT ONLY (nessuna implementazione, nessun refactor) · **Evidenza:** codice del repository `/app` (backend FastAPI `app/routers` 66 router / ~19.7k righe; frontend React `src/pages` 60 pagine / ~13.4k righe; 92 file pytest, 1224 passed nell'ultima suite).

**Legenda STATUS:** EXISTS = comportamento end-to-end funzionante (API + UI o API verificata da test) · PARTIAL = modello/API/UI incompleti o solo una delle due facce · MISSING = nessuna evidenza nel codice · EXTERNAL_INTEGRATION = da delegare a servizio terzo · NOT_NEEDED_NOW.
**Colonne compresse:** BE = backend source · FE = frontend source · SoT = source of truth (collection Mongo) · Roles = permission keys (`app/permissions.py`, 247 chiavi) · Test = file in `backend/tests/` · Prio = priorità raccomandata.

---

## EXECUTIVE_SUMMARY

Panorama Pilot è oggi un **CPQ + Contract + Technical Workflow verticale molto profondo** (catalogo reale, motori pricing multipli, margine/commissione RBAC, contratto con snapshot immutabile e firma elettronica semplice, rilievo → abaco → ordine esecutivo → release produzione) con un **CRM operativo completo** (lead, pipeline, attività, task, appuntamenti, inbox, consensi, webhook intake, handoff SLA) e una **tesoreria/controllo di gestione modellati ma poco cablati alla realtà operativa**.
I domini "downstream" (**procurement, magazzino, produzione, logistica, posa, assistenza, amministrazione**) esistono come **CRUD + state machine di base con UI generica** (`ErpModulePages.jsx`: 11 pagine in 332 righe, list + create form), senza motori (MRP, capacità, riserve, lotti, 3-way match, SLA ticket, garanzie).
**Nessun motore trasversale di "Control Tower"**: rilevazione automatica di rischi limitata a handoff overdue, task in ritardo, 3 suggerimenti AI-CFO rule-based, KPI dashboard. Nessuno scheduler (`.emergent/crons.yml` assente; solo un retry-worker email in-process).
**Compliance fiscale italiana**: IVA/ritenute/F24 modellati come registri interni; fatturazione elettronica SDI, contabilità generale, paghe = **EXTERNAL_INTEGRATION** (nessuna evidenza nativa, corretto non inventarla).

### CURRENT_COMPLETION_BY_DOMAIN %
| # | Dominio | % | Sintesi |
|---|---|---|---|
| 01 | CRM / Lead | **70** | Lead CRUD+kanban+convert, webhook intake con dedup, consensi, inbox, template, automazioni email (modello), handoff SLA. Manca scoring, routing automatico, SLA prima risposta, sequenze |
| 02 | Sales / Opportunity | **55** | Pipeline/stage/probability/estimated_value/lost_reason, goals, commission plans+entries+invoices. Manca forecast pesato, aging/stale alert, quota per territorio |
| 03 | Customer 360 | **65** | Customer master + numero, tipi, tab anagrafica/cantieri/preventivi/timeline, portale cliente (jobs/documents/tickets), email eventi. Manca decision makers, credit status, storico pagamenti/installazioni nella scheda |
| 04 | Site / Property | **60** | Sites CRUD con indirizzo obbligatorio validato, condizioni cantiere + supplementi accesso. Manca foto/documenti per cantiere e dati catastali strutturati |
| 05 | CPQ / Quoting / Pricing | **85** | Il dominio più maturo: catalogo reale (finestre/zanzariere/tapparelle/cassonetti GRID), motori pricing v3/multi-cat/parametrico, margine dual, commissione modulare, floor >15%, sconti/promo, pagamenti, consegna, PDF premium, link pubblico, revisioni, snapshot |
| 06 | Contract Management | **85** | Accepted→Contract V1, snapshot immutabile, termini generali canonici, pre-firma check, firma canvas+OTP, PDF versionato con hash, variation/superseded, portale cliente |
| 07 | Survey / Engineering | **70** | Rilievo, compare-quote, abaco tecnico (versioning, firma pubblica con consensi), executive order, variances, release-check produzione. Manca scheduling squadre rilievo, foto misure, mobile |
| 08 | Procurement | **35** | Suppliers, supplier price lists, PO+status, goods receipt, NC fornitore. Manca RFQ, comparazione, requisition/approvazione, 3-way match, performance |
| 09 | Inventory / WMS | **30** | Items, locations, movements, levels, counts, dashboard. Manca riserve, lotti/seriali, barcode workflow, picking/kitting, van stock |
| 10 | Production / MRP / MES | **35** | BOM, production orders (state machine), cutting list FFD 1D, phase log, KPI. Manca MRP, capacità, scheduling, shop-floor UI, consumo materiali, OEE |
| 11 | Logistics / Delivery | **35** | Finished-good packs, shipments/DDT status, nessun tracking/POD/route |
| 12 | Installation / Field Service | **40** | Crews, installation plans, reports con submit, dashboard installer. Manca mobile checklist, foto, accettazione cliente firmata, punch list, job costing |
| 13 | Change Order / Variation | **60** | Quote revision (R00→R01), contract create-variation/superseded, workflow variances. Manca change order economico post-firma con approvazione cliente |
| 14 | Support / Warranty | **30** | Service tickets + stato + KPI + email cliente + portale. Manca SLA, asset installati, garanzia, ricambi, CSAT/NPS |
| 15 | Accounting / Control | **45** | Invoices/payments/payment plans, payables/receivables, fixed/personnel costs, budget scenari, break-even, investimenti, profitability per contratto. Manca AR/AP aging, cost center, job accounting reale, integrazione contabile |
| 16 | Treasury / Cash Flow | **45** | Bank accounts, fondi virtuali, incassi, allocation policy, IVA entries/closing, F24, transfers suggest/approve, import estratti, riconciliazione auto, scenari mensili. Alert: modello + endpoint ma **nessuna generazione** |
| 17 | CFO / FP&A | **50** | Budget scenari (3 preset), simulate what-if, break-even, consolidato, AI-CFO 3 regole. Manca rolling forecast, P&L/SP, forecast vs actual, variance analysis |
| 18 | HR / Workforce | **10** | Solo personnel_costs. Nessun HR |
| 19 | DMS / Compliance | **55** | Attachments, storage privato (Local/S3), PDF versionati hash, termini generali canonici, audit log immutabile, consensi. Manca retention, classificazione documentale, scadenze compliance |
| 20 | BI / AI / Control Tower | **35** | Dashboard per ruolo, KPI quotes/direction, margin-control company dashboard, AI-CFO suggestions. Nessun motore risk→owner→task→azione |
| 21 | Multi-company / Governance | **65** | Legal entities, intercompany mirroring/riconciliazione, consolidamento, SaaS plans/entitlements, module gating (usato solo in 2 router) |
| 22 | Platform / Security / Integrations | **75** | JWT + sessioni + brute force + rate limiter + RBAC 247 permessi + audit + tenant isolation + registrazione self-service + onboarding + email provider/DNS + storage + webhook lead. MFA solo flag modello; WhatsApp/email reali = config provider |

**Completamento medio ponderato: ~52%** (golden thread coperto E2E fino a "release produzione"; da lì in giù è CRUD).

---

## 01 CRM / LEAD MANAGEMENT
| Capability | Status | Implementation / evidence | Roles | Limits / Security | Test | Prio |
|---|---|---|---|---|---|---|
| Lead ingestion (form, landing, webhook) | EXISTS | BE `routers/leads.py` (7 ep), `routers/landing.py` public intake, `routers/ops_workflow.py` `/integrations/leads/webhook/{slug}` + verify + ingestions log; FE `LeadsPage`, `LeadDetailPage`, `LandingPage` | crm.leads.*, leads.webhook.manage | Provider Meta/Google Ads NON collegati (webhook generico) | crm_m2_test, test_ops_m6 | P1 |
| Lead deduplication | EXISTS | `landing.py::_dedup_key` SHA256(email+phone+vat); `ops_workflow.py::_dedup_lead_key` | — | Solo hash esatto, no fuzzy | test m7 landing | P2 |
| Lead source / source_detail | EXISTS | `models_crm.Lead.source/source_detail` | — | — | crm_m2 | — |
| Campaign attribution (UTM) | PARTIAL | campo `campaign` in ops_workflow ingestion; nessun UTM/costo campagna | — | — | — | P2 |
| Consent (GDPR) | EXISTS | `/ops/consents` GET/POST/revoke | — | — | test_ops_m6 | — |
| Lead scoring | MISSING | solo `probability` manuale | — | — | — | P1 |
| Lead routing automatico | PARTIAL | `assignment-rules` + `user-groups` (ops_workflow) usati per handoff, non per lead | crm.leads.assign | — | test_ops_m6 | P1 |
| First-response SLA | PARTIAL | SLA solo su handoff operativi (`handoff_engine.sla_ack_minutes`, `scan-overdue`) | — | scan manuale via endpoint, no scheduler | test_ops_m6 | P1 |
| Activities / tasks / next action | EXISTS | `activities.py`, `tasks.py`, `Lead.next_action_at/note`; FE TasksPage, timeline | crm.activities.*, crm.tasks.* | — | crm_m2 | — |
| Appointment booking + reminders + no-show | PARTIAL | `appointments.py` CRUD, `reminder_minutes`, status `no_show`; nessun invio reminder (no scheduler) | crm.appointments.* | — | crm_m2 | P2 |
| Email / phone / WhatsApp | PARTIAL | `activities/send-email`, `/log-call`, `/send-whatsapp`; provider WhatsApp `mock` default, email provider configurabile (`email_service.py`) | crm.comms.* | Email reale richiede RESEND/SMTP; WhatsApp = EXTERNAL_INTEGRATION | test_email_service | P1 |
| Inbox / conversazioni / template | EXISTS (API) | `/ops/inbox/*`, `/ops/message-templates` | — | FE minima (WhatsAppLogsPage) | test_ops_m6 | P2 |
| Sales sequences / email automation | PARTIAL | `/ops/email-automations` CRUD modello; nessun esecutore | — | no scheduler | — | P2 |

## 02 SALES / OPPORTUNITY
| Capability | Status | Implementation | Roles | Limits | Test | Prio |
|---|---|---|---|---|---|---|
| Pipeline / stages / kanban | EXISTS | `pipelines.py`, `leads/kanban`; FE LeadsPage kanban | crm.pipelines.* | — | crm_m2 | — |
| Opportunity probability / estimated value | EXISTS | `Lead.probability/estimated_value/currency` | — | manuale | crm_m2 | — |
| Deal aging / stale alerts | MISSING | nessun calcolo su `last_activity_at` | — | — | — | P1 |
| Lost reasons | EXISTS | `Lead.lost_reason`, `bi.py::_rejection_reasons` | — | — | — | — |
| Sales forecast | PARTIAL | `bi.py::_pipeline_weighted_value` (KPI), nessun forecast per periodo | bi.direction.view | — | test_code_quality | P1 |
| Quota / targets / goals | EXISTS | `sales.py /goals`, `margin_control /targets`; FE GoalsPage | crm.goals.* | — | test_margin_control | — |
| Commission | EXISTS | `commission_engine.py`, `margin_engine.py` (modular by discount, floor >15%), `/ops/commission-plans|entries|invoices` approve/pay; FE CommissionTachometer | commission.* | — | test_margin_dynamic_commission (59), test_ops_m6 | — |
| Territory | MISSING | — | — | — | — | P3 |
| Cross-sell / upsell | PARTIAL | `Lead.interested_products`, service resolver automatico nel preventivo | — | nessuna raccomandazione | — | P3 |
| Referral / review / campaign ROI / CAC | MISSING | — | — | — | — | P3 |

## 03 CUSTOMER 360
| Capability | Status | Implementation | Roles | Limits | Test | Prio |
|---|---|---|---|---|---|---|
| Customer master (private/company, tax_code, vat, sdi, pec, numero) | EXISTS | `customers.py`, `customer_number.py`, `customer_validation.py`; FE CustomersPage/CustomerDetailPage | crm.customers.* | — | test_m1_part2, test_customer_quote_fast_flow | — |
| Contacts / decision makers | PARTIAL | `contacts.py` CRUD; nessun ruolo decisionale | crm.contacts.* | — | — | P2 |
| Multiple sites | EXISTS | `sites.py` + tab cantieri | — | — | test_m1_part2 | — |
| Documents / photos | PARTIAL | `attachments.py` generico; non collegati alla scheda cliente in UI | attachments.* | — | — | P2 |
| Communication history / timeline | EXISTS | `customer_timeline.py`, `timeline.py`; tab timeline | crm.activities.view | — | test_m1_part2 | — |
| Quotes / contracts nella scheda | EXISTS | tab preventivi + Fast Flow (`customer-create-quote`) | — | — | test_customer_quote_fast_flow | — |
| Orders / payments / installations / support nella scheda | MISSING (in UI) | dati esistono nei moduli ma non aggregati in Customer 360 | — | — | — | P1 |
| Customer portal | EXISTS | `customer_portal.py` (auth, jobs, documents, tickets, tracking mapping), FE CustomerPortal | customer_portal.* | — | test_customer_portal_core_v1, iter39 | — |
| Credit status / limite | MISSING | — | — | — | — | P2 |

## 04 SITE / PROPERTY
| Capability | Status | Implementation | Limits | Test | Prio |
|---|---|---|---|---|---|
| Site CRUD con indirizzo completo obbligatorio | EXISTS | `sites.py` (`SITE_ADDRESS_REQUIRED`), `NewQuoteDialog` inline site form | — | test_m1_part2 | — |
| Site conditions + supplementi accesso | EXISTS | `access_rules.py`, `SiteConditionsForm`, regole seed | — | iteration_15 | — |
| Foto / documenti cantiere / catasto | MISSING | — | — | — | P2 |

## 05 CPQ / QUOTING / PRICING
| Capability | Status | Implementation | Roles | Limits | Test | Prio |
|---|---|---|---|---|---|---|
| Catalog reale + categorie + colori | EXISTS | `catalog.py`, `product_catalog.py`, `product_categories.py`, `product_colors.py`, seed F1 | catalog.*, products.* | 7 prodotti legacy TO_CONFIRM | test_f1_real_catalog, test_catalog_area | — |
| Price lists + versioning + importer | EXISTS | `parametric.py` item_pricelists, `importer.py` (draft/publish/rollback), gating `PRICELIST_NOT_PUBLISHED` | pricelists.*, catalog.import | — | test_pricelist_gating_iter22, test_blocco_bcd | — |
| Configuration rules / visual renderer | EXISTS | `multi_category_configurator.py`, `geometry_engine.py`, `svg_advanced.py`, `composite_drawing.py`, `color_engine.py`; FE MultiCategoryConfiguratorDialog, GeometryBuilderPage | — | Vano Model V2 non iniziato | test_multi_category_*, test_p0_visuals_* | — |
| BOM + technical costing | EXISTS | `bom_engine_v2.py`, `bom_recipes.py` (20), `pricing_v3` (technical_recipes, workshop_cost) | parametric.bom.* | — | test_bom_engine_blocco_a, test_pricing_v3_milestone1 | — |
| Commercial pricing / multiplier / promotions / discounts | EXISTS | `commercial_pricing_rules`, `quotes.py` global/promo/payment discount, `_raise_if_price_blocked` | quotes.apply_discount / override_discount | — | test_global_discount_msg407 | — |
| Margin guard + commission (dual RBAC) | EXISTS | `margin_engine.py` v3, snapshot redaction `COMMERCIAL_SAFE_KEYS`, PDF strip | quotes.view_margins, Admin Master | — | test_margin_* (150+) | — |
| VAT / regime / detrazione | EXISTS | `vat_regime`, `tax_deduction_requested`, `treasury/tax-deduction-rates` | — | — | test_audit_v1_sez20 | — |
| Payment methods / terms | EXISTS | `payment_terms.py` (codici, sconto FULL_UPFRONT, piano) | — | — | test_quote_editor_v1 | — |
| Financing | MISSING | — | — | EXTERNAL_INTEGRATION (finanziarie) | — | P3 |
| Delivery promise | PARTIAL | `delivery_policy.py` (modalità + supplemento + testo), nessuna data promessa da capacità | — | — | — | P2 |
| Services / installation / accessories | EXISTS | `service_resolver.py`, `simple_services.py`, installation_mode, ENEA, smaltimento | — | costi interni ENEA/DISPOSAL NEEDS_PO | test_installation_mode_v1 | — |
| Quote revisions | EXISTS | `quotes.py` revise (R00→R01, is_current) | quotes.edit | — | m3_quotes_test | — |
| Approvals (sconto oltre soglia) | EXISTS | `approval` flow + DIRECTOR_APPROVAL >30% | quotes.approve | — | m3_quotes_test | — |
| PDF (premium, versionato, no leak) | EXISTS | `pdf_router.py` (19 ep), `pdf_renderer.py`, templates | quotes.*_pdf | — | test_quote_pdf_premium_v2, test_msg407_pdf_rbac | — |
| Acceptance (link pubblico, firma, OTP) | EXISTS | `public.py`, `signature.py`, `otp.py` (Redis) | quotes.public_* | Redis fail-closed in prod | test_public_link_m333, test_public_signature_m334 | — |
| Snapshots (price/financial/technical) | EXISTS | `price_snapshot` freeze on sent, financial freeze on accepted, `calculation_hash` | — | — | test_contract_source_of_truth | — |

## 06 CONTRACT MANAGEMENT
| Capability | Status | Implementation | Roles | Test | Prio |
|---|---|---|---|---|---|
| Accepted quote → contract (idempotente, prefill) | EXISTS | `contracts.py` (22 ep) + `contracts_helpers.py` | quotes.convert_contract, contracts.generate | test_accepted_quote_to_contract_v1, iter47 | — |
| Contract snapshot immutabile + hash | EXISTS | `build_contract_snapshot`, `compute_snapshot_hash`, `build_signed_snapshot` | — | idem | — |
| General terms canonici + hash | EXISTS | `general_terms_canonical.py`, `/general-terms/verify` | — | idem | — |
| Pre-sign validation | EXISTS | `presign_errors` (10 codici) | — | idem | — |
| Modifica anagrafica pre-firma con sync/audit; blocco economico | EXISTS | `PATCH /parties` (CUSTOMER_EDITABLE_KEYS), `CONTRACT_REVISION_REQUIRED` 409 | contracts.edit_draft | iter47 | — |
| Signatures | EXISTS (FES) | canvas + OTP, `signature_provider.py` adapter `internal_canvas` | contracts.sign | FEA/FEQ = EXTERNAL_INTEGRATION (Namirial/InfoCert/Aruba) | test_fase2_pdf_otp_storage | P2 |
| Contract revisions / variation | EXISTS | `create-variation` → superseded | contracts.create_variation | test_blocco_bcd_iter20 | — |
| Specific approvals (clausole) | EXISTS | clauses + templates | quotes.manage_clauses | — | — |

## 07 TECHNICAL SURVEY / ENGINEERING
| Capability | Status | Implementation | Test | Prio |
|---|---|---|---|---|
| Survey auto da contratto firmato + status flow | EXISTS | `workflow_engine.ensure_survey_from_contract`, `surveys.py` | test_workflow_m6_wf | — |
| Survey scheduling (squadra/data) | PARTIAL | `Survey.scheduled_*`; nessun calendario squadre rilievo | — | P2 |
| Measurement capture | EXISTS (desktop) | `SurveyOpening` misure; FE SurveysPage generica | test_stabilization_rc1 | P1 (mobile) |
| Photos | MISSING | — | — | P2 |
| Quote-vs-survey variance | EXISTS | `/surveys/{sid}/compare-quote`, `Variance` workflow | test_stabilization_rc1 | — |
| Technical approval (abaco, firma cliente con consensi) | EXISTS | `workflow.py` technical-schedules + public sign + executive order | test_workflow_m6_wf | — |
| Production lock / release check + override | EXISTS | `/workflow/production/release-check`, `release-override` (2° approvatore) | test_workflow_m6_wf | — |

## 08 PROCUREMENT
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Supplier master | EXISTS | `purchasing.py /suppliers` CRUD; FE SuppliersPage (generica) | — |
| Supplier price lists / lead times | PARTIAL | `/supplier-price-lists` (entries); `lead_time_days` campo, nessun uso | P2 |
| RFQ / supplier comparison | MISSING | — | P2 |
| Purchase requisition / approval | MISSING | — | P2 |
| Purchase order + status | EXISTS | `/purchase-orders` + `/status` (OFR-) | — |
| Supplier confirmation / expected delivery | PARTIAL | campi su PO, nessun workflow | P2 |
| Goods receipt | EXISTS | `/goods-receipts` (RIC-) → stock movement | — |
| Purchase returns | MISSING | — | P3 |
| Supplier NC | EXISTS | `/goods-receipts/non-conformities` | — |
| Supplier performance / risk | MISSING | — | P3 |
| 3-way match | MISSING | — | P2 |
| Subcontracting | MISSING | — | P3 |
Test: test_ops_m6, test_stabilization_rc1 (CRUD).

## 09 INVENTORY / WMS
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Warehouses / locations | EXISTS | `/stock-locations` | — |
| On-hand / levels / movements / counts | EXISTS | `/stock/movements`, `/stock/levels`, `/inventory-counts` (+lines/close), dashboard | — |
| Available vs reserved / job reservation | MISSING | — | P1 |
| Replenishment / safety stock / reorder | PARTIAL | `Item.min_stock`, nessun alert generato | P2 |
| Lot / serial | MISSING | — | P3 |
| Barcode | PARTIAL | campo `barcode` su Item, nessun flusso scan | P3 |
| Receiving / put-away / picking / kitting / job staging | MISSING | — | P2 |
| Van inventory / transfers / quarantine / dead stock / stockout warning | MISSING | — | P3 |
Test: test_stabilization_rc1 TestItemsAndStock.

## 10 PRODUCTION / MRP / MES
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| BOM (produzione) | EXISTS | `production.py /boms`, + BOM parametrica CPQ | — |
| Production orders + state machine | EXISTS | `/production-orders` (OPR-) stati waiting_validation→…→completed | — |
| Cut optimization 1D | EXISTS | FFD `cutting-lists`, `nesting.py` | — |
| Glass optimization / CNC integration | MISSING | — | P3 / EXTERNAL |
| Routing / work centers / capacity / finite scheduling / MPS / MRP | MISSING | — | P1 |
| Shop-floor UI / barcode / labor time | PARTIAL | `/production-phases` log; nessuna UI operatore | P2 |
| Material consumption / WIP / scrap / rework | PARTIAL | `color_scrap.py` sfrido in BOM; nessun consumo reale | P2 |
| Quality (QC checks, NC) | EXISTS | `qc.py` checklists, NC resolve, KPI | — |
| OEE / maintenance / production ETA / bottleneck / planned vs actual cost | MISSING | — | P2 |
Test: test_ops_m6.

## 11 LOGISTICS / DELIVERY
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Packaging (finished good packs) | EXISTS | `/finished-good-packs` (PF-) | — |
| Shipment / DDT + status | EXISTS | `/shipments` (DDT-) | — |
| Loading / vehicles / routes / tracking / POD | MISSING | — | P2 |

## 12 INSTALLATION / FIELD SERVICE
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Crews / skills | PARTIAL | `/installation-crews` (no skills) | P2 |
| Installation plans + status | EXISTS | `/installation-plans` (POS-) | — |
| Material readiness | PARTIAL | `release-check` produzione; nessun check materiali posa | P2 |
| Mobile work order / checklists / photos | MISSING | — | P1 |
| Installation report + submit | EXISTS | `/installation-reports/{rid}/submit` | — |
| Customer acceptance firmata / punch list / NC posa | PARTIAL | NC generico QC; nessuna firma cliente in posa | P1 |
| Job costing (planned vs actual) | PARTIAL | `profitability/{contract_id}` su snapshot, nessun actual | P1 |

## 13 CHANGE ORDER / VARIATION
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Quote revision | EXISTS | `quotes.py revise` | — |
| Contract variation / superseded | EXISTS | `contracts.py create-variation` | — |
| Variances tecniche (rilievo/abaco) | EXISTS | `/workflow/variances` (VAR) | — |
| Change order economico post-firma con approvazione cliente | MISSING | — | P1 |

## 14 SUPPORT / WARRANTY / INSTALLED ASSETS
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Tickets + status + KPI + email cliente + portale | EXISTS | `service_tickets.py` (ASS-), `customer_email_events.py`, `customer_portal /tickets` | — |
| SLA / priorities | PARTIAL | campo priority; nessun SLA | P1 |
| Customer-visible vs internal notes | EXISTS | `internal_notes` vs `notes` (test email) | — |
| Installed assets / serial-QR / warranty | MISSING | — | P1 |
| Diagnosis / parts / field service / supplier recovery / root cause | MISSING | — | P2 |
| CSAT / NPS / reviews / referrals | MISSING | — | P3 |

## 15 ACCOUNTING / MANAGEMENT CONTROL
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| AR (invoices, payments, payment plans) | EXISTS | `admin_finance.py` (FT-), KPI | — |
| AP (payables) | EXISTS | `management_control /payables` + pay | — |
| AR/AP aging / scadenziario | PARTIAL | `Payable/Receivable` con due_date; nessuna vista aging | P1 |
| Banking / reconciliation | EXISTS (base) | `treasury /statements/import`, `/reconcile/auto` | — |
| Accounting integration (contabilità generale) | EXTERNAL_INTEGRATION | nessuna evidenza nativa | P1 |
| Fattura elettronica SDI / FatturaPA | EXTERNAL_INTEGRATION | nessun XML/SDI nel codice | P1 |
| Cost centers / analytic accounting | MISSING | `ManagementAccount` piano conti gestionale, no CdC | P2 |
| Job accounting / profitability per commessa | PARTIAL | `profitability/{contract_id}` + `margin_control` (snapshot, no actual) | P1 |
| Budget vs actual | PARTIAL | budget scenari, actual non collegato | P1 |
| Profitability per prodotto / venditore / canale / sede | PARTIAL | dashboard sales-team (commissioni); nessun per prodotto/canale | P2 |
| IVA / ritenute / F24 (registri interni) | EXISTS (NATIVE, gestionale non fiscale) | `treasury /vat/*`, `/withholding/calculate`, `/f24` | — |

## 16 TREASURY / CASH FLOW
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Bank balances / cash position / fondi virtuali | EXISTS | `treasury.py` bank-accounts, funds, allocation policy/runs, dashboard | — |
| AR/AP schedule → expected collections/payments | PARTIAL | dati esistono, nessuna proiezione per settimana | P1 |
| Payroll / tax / debt / financing | PARTIAL | F24 + VAT closing; payroll/debt assenti | P2 |
| Forecast 2/4/8/13 settimane | MISSING | `TreasuryScenario.horizon_months` solo mensile con input manuali (`monthly_income/expenses`) | P1 |
| Scenari base/prudent/stress | EXISTS (modello) | `scenario_kind`, compute lineare | — |
| DSO / DPO / min cash buffer / cash-gap alert | PARTIAL | `TreasuryAlert` modello + GET/resolve, **0 punti di generazione** nel codice | P1 |
| Working capital | MISSING | — | P2 |
Test: test_m7_treasury_consolidation.

## 17 CFO / FP&A
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Annual budget / scenari / simulate what-if | EXISTS | `management_control /budget/*`, `breakeven.py` 3 preset | — |
| Rolling forecast / forecast vs actual / variance analysis | PARTIAL | `promote-forecast` esiste; actual non alimentato | P1 |
| P&L / balance sheet / cash flow statement | PARTIAL | `financial_statements.view/import` permessi; nessun endpoint riclassifica | P2 |
| Break-even / EBITDA | EXISTS | `breakeven.compute_budget_outputs` | — |
| Headcount / driver-based / OPEX / CAPEX | PARTIAL | fixed/personnel costs + investments | P2 |
| Investment ROI / payback / funding needs | PARTIAL | `Investment` modello, no ROI calc | P3 |
| Group consolidation | EXISTS | `consolidation.py` con eliminazioni intercompany | — |
| AI-CFO | PARTIAL | `ai_cfo.py` 3 regole (cash, receivables, conversion) + `treasury/ai-cfo/run` 3 insight | P2 |

## 18 HR / WORKFORCE
| Capability | Status | Prio |
|---|---|---|
| Personnel costs | EXISTS (`personnel-costs`) | — |
| Anagrafica dipendenti / presenze / timesheet / ferie / skills / paghe | MISSING → paghe EXTERNAL_INTEGRATION | P3 |

## 19 DMS / COMPLIANCE
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Attachments + storage privato (Local/S3 signed URL) | EXISTS | `attachments.py`, `storage.py`, `object_storage.py` | — |
| Versioned PDF + hash | EXISTS | `pdf_router.py`, contracts pdf versions | — |
| General terms canonical + hash | EXISTS | `general_terms_canonical.py` | — |
| Audit log immutabile | EXISTS | `services/audit.py`, `AuditPage` | — |
| Consent registry | EXISTS | `/ops/consents` | — |
| Retention policy / classificazione documentale / scadenze (DURC, certificazioni) | MISSING | — | P2 |
| Documenti ENEA / pratiche | PARTIAL | servizio ENEA prezzato, nessun fascicolo | P2 |

## 20 BI / AI / CONTROL TOWER
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Dashboard per ruolo (sales/direction/production/installer) | EXISTS | `dashboards_crm.py`, `dashboard.py`, `Dashboard.jsx` | — |
| KPI quotes / direction / margin company | EXISTS | `bi.py`, `margin_control /company-dashboard` | — |
| Alert engine trasversale | MISSING | vedi CONTROL TOWER AUDIT | P0 |
| Scheduler / job ricorrenti | MISSING | nessun `.emergent/crons.yml`; solo `email_service._retry_worker` | P0 |

## 21 MULTI-COMPANY / GOVERNANCE
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Legal entities + membership | EXISTS | `legal_entities.py`; FE LegalEntitiesPage | — |
| Intercompany mirroring / riconciliazione / storno | EXISTS | `intercompany.py` | — |
| Consolidation | EXISTS | `consolidation.py` | — |
| SaaS plans / entitlements / module gating | PARTIAL | `saas_platform.py`, `module_gating.require_module` usato solo in `intercompany` (6) e `management_control` (25) | P2 |
| Tenant isolation | EXISTS | filtro `tenant_id` su tutte le query, test dedicati | — |

## 22 PLATFORM / SECURITY / INTEGRATIONS
| Capability | Status | Implementation | Prio |
|---|---|---|---|
| Auth JWT + refresh + sessioni + logout-all | EXISTS | `auth.py`, `sessions.py`, `auth_helpers.py` | — |
| Brute force / rate limiting | EXISTS | `rate_limiter.py`, `check_brute_force` (evidenza: 429 nei test) | — |
| RBAC 247 permessi + ruoli protetti + Admin Master | EXISTS | `permissions.py`, `roles.py`, `_get_perms` | — |
| MFA | PARTIAL | flag su `models.py`; nessun endpoint TOTP in `auth.py` | P2 |
| Self-registration + approvazione + onboarding | EXISTS | `registration.py`, `onboarding.py` | — |
| Google Sign-in | PARTIAL | `test_google_signin` presente; direttiva msg 368 congelata | P1 |
| Audit trail | EXISTS | `audit.py` | — |
| Email provider + DNS check + logs + templates | EXISTS (config) | `email_service.py`, `email_dns.py`, `email_settings.py`, `email_logs.py` | SMTP live test post-deploy |
| WhatsApp | EXTERNAL_INTEGRATION | `whatsapp.py` provider mock/adapter | P2 |
| Object storage | EXISTS (Local) / S3 config | `storage.py` | — |
| Webhook intake lead | EXISTS | `/integrations/leads/webhook/{slug}` | — |
| Public APIs / API keys per integratori | MISSING | — | P3 |
| Formula security (no eval) | EXISTS | `formula_security.py` guard | — |

---

## CONTROL TOWER AUDIT (rilevare e agire)
Legenda: D=CAN_DETECT · Q=CAN_QUANTIFY_IMPACT · O=CAN_ASSIGN_OWNER · T=CAN_CREATE_TASK · R=CAN_RECOMMEND_ACTION · X=CAN_EXECUTE_ACTION. ✅ nativo · ◐ parziale/manuale · ✗ assente.
| Rischio | D | Q | O | T | R | X | Evidenza |
|---|---|---|---|---|---|---|---|
| Lead response delay | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | nessun SLA lead; SLA solo handoff (`scan-overdue` manuale) |
| Stale opportunity | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | `last_activity_at` esiste, nessun calcolo |
| Missing follow-up | ◐ | ✗ | ✅ | ✅ | ✗ | ✗ | `tasks_overdue` in dashboard; task assegnabili manualmente |
| Pipeline forecast risk | ◐ | ◐ | ✗ | ✗ | ◐ | ✗ | `_pipeline_weighted_value`, `_conversion_suggestion` AI-CFO |
| Salesperson underperformance | ◐ | ✗ | ✗ | ✗ | ✗ | ✗ | dashboard sales-team + goals, nessun alert |
| Excessive discount | ✅ | ✅ | ✗ | ✗ | ✅ | ✅ | `DISCOUNT_BLOCKED_MARGIN_FLOOR`, DIRECTOR_APPROVAL >30%, max_discount |
| Margin erosion | ✅ | ✅ | ✗ | ✗ | ◐ | ◐ | margin engine, bande, banner CRITICO, freeze on accepted |
| Missing customer data | ✅ | ✗ | ✗ | ✗ | ✅ | ✗ | `presign_errors` 10 codici + UI presign-errors |
| Supplier delay | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | `expected_delivery` campo, nessun confronto |
| Material shortage / stockout | ◐ | ✗ | ✗ | ✗ | ✗ | ✗ | `min_stock` + levels, nessun alert |
| Production overload / bottleneck | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | nessuna capacità |
| Survey discrepancy | ✅ | ✅ | ✗ | ✗ | ✗ | ◐ | compare-quote + Variance + release-check blocca |
| Installation overload | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| Late receivable | ◐ | ◐ | ✗ | ✗ | ◐ | ✗ | `_receivables_suggestion` AI-CFO; nessun aging |
| Customer credit risk | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| Cash gap | ◐ | ◐ | ✗ | ✗ | ◐ | ◐ | `_cash_flow_suggestion`, transfers suggest/approve; `TreasuryAlert` mai generato |
| Forecast miss | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | actual non collegato |
| Warranty recurrence / quality problem | ◐ | ✗ | ✗ | ✗ | ✗ | ✗ | QC NC + tickets KPI, nessuna ricorrenza |
| Missing document | ◐ | ✗ | ✗ | ✗ | ✗ | ✗ | solo presign/pricelist gating |
| Compliance gate | ◐ | ✗ | ✗ | ✗ | ✗ | ✅ | gating listini non pubblicati, release-check produzione, fail-closed pricing |
**Verdetto:** Panorama **rileva bene i rischi commerciali interni al preventivo/contratto** (sconto, margine, dati mancanti, varianze) e **blocca** (fail-closed). Non esiste un layer "risk → owner → task → azione" né uno scheduler: tutto è on-request.

---

## TOP_20_EXISTING_STRENGTHS
1. Motore pricing tecnico/commerciale fail-closed con snapshot + hash deterministico (`pricing_v3`, `multi_category_pricing`).
2. Catalogo reale 4 famiglie con griglia cassonetti 4.464 celle importata dal listino PO.
3. Margin Engine v3 dual (Admin Master vs commerciale) con redaction server-side e PDF strip ricorsivo.
4. Commissione modulare per fascia sconto + floor >15% + tachimetro UI.
5. Contract V1: snapshot immutabile, termini canonici con hash, pre-sign check, blocco `CONTRACT_REVISION_REQUIRED`.
6. Firma elettronica semplice con OTP Redis fail-closed e PDF versionati con SHA-256.
7. Workflow tecnico completo: survey → abaco → firma cliente con 6 consensi → executive order → release-check con override a 2 approvatori.
8. Gating listini non pubblicati (`PRICELIST_NOT_PUBLISHED`) che blocca invio preventivo.
9. Quote Revision (R00→R01) con `is_current`, freeze price/financial snapshot.
10. Fast Flow cliente→preventivo con selettore ricercabile + creazione inline senza duplicati.
11. Customer Portal con auth separata, documenti, tracking mappato per stato, ticket.
12. Email eventi cliente idempotenti, destinatario risolto server-side, nessun leak interno.
13. Lead webhook intake con dedup, consensi GDPR, inbox conversazioni.
14. Handoff operativi con SLA ack e stato overdue.
15. Intercompany auto-mirroring + riconciliazione + consolidato con eliminazioni.
16. Budget scenari / break-even / what-if a 20+ variabili.
17. Tesoreria: fondi virtuali, allocation policy, IVA/F24 registri, import estratti + riconciliazione auto.
18. RBAC granulare 247 permessi + ruoli protetti + tenant isolation testata.
19. Sicurezza: brute force, rate limiting, no-eval guard, audit immutabile, secrets scrubbing nei test.
20. Suite pytest 1224 verdi + testing E2E Playwright ripetibile.

## TOP_30_CRITICAL_GAPS
1. Nessun scheduler / job ricorrente (alert, reminder, SLA, automazioni email mai eseguiti).
2. Nessun Control Tower engine (risk→owner→task).
3. `TreasuryAlert` mai generato (endpoint vuoto).
4. Forecast di cassa settimanale (2/4/8/13w) assente; scenari solo mensili con input manuali.
5. Actual non collegato a budget (forecast vs actual, variance) — dashboard finanziarie "vuote di realtà".
6. Nessun AR/AP aging né DSO/DPO.
7. Lead scoring, routing automatico, SLA prima risposta assenti.
8. Stale opportunity / deal aging alert assenti.
9. Sales forecast per periodo assente.
10. Customer 360: ordini, pagamenti, installazioni, assistenza non aggregati in scheda.
11. Credit status cliente assente.
12. Riserve materiali per commessa (available vs reserved) assenti.
13. MRP / capacità / scheduling produzione assenti.
14. Shop-floor UI e consumo materiali reali assenti.
15. Job costing actual (posa/produzione) assente → profitability solo su snapshot.
16. Mobile work order / checklist / foto posa assenti.
17. Accettazione cliente firmata in posa + punch list assenti.
18. Change order economico post-firma con approvazione cliente assente.
19. Asset installati / seriali / garanzia assenti.
20. SLA ticket assistenza assente.
21. RFQ / comparazione fornitori / 3-way match assenti.
22. Tracking spedizioni / POD / percorsi assenti.
23. Foto e documenti per cantiere/cliente non collegati.
24. Reminder appuntamenti non inviati.
25. Email automations senza esecutore.
26. MFA non implementata (solo flag).
27. Google Sign-in congelato.
28. Module gating applicato solo a 2 router (entitlement SaaS non enforce sugli altri 60).
29. UI generica `ErpModulePages` per 11 moduli operativi (list+create), nessun dettaglio/stato/azioni.
30. Documentazione compliance (retention, scadenze certificazioni, fascicolo ENEA) assente.

## TOP_20_INTEGRATION_CANDIDATES
1. Fatturazione elettronica SDI (Aruba/Fatture in Cloud/TeamSystem API).
2. Contabilità generale (TeamSystem/Zucchetti/Fatture in Cloud export).
3. Paghe / HR (Zucchetti, Factorial).
4. Firma FEA/FEQ (Namirial, InfoCert, Aruba) — adapter già pronto.
5. Email transazionale (Resend/SendGrid/SMTP) — adapter pronto, SMTP live post-deploy.
6. WhatsApp Business API (Meta Cloud API / Twilio) — adapter pronto.
7. Meta Lead Ads / Google Ads lead form → webhook esistente.
8. Google Calendar / Outlook per appuntamenti e squadre.
9. Open Banking PSD2 (Fabrick, Tink) per saldi/movimenti reali.
10. Pagamenti online caparra (Stripe) su link pubblico preventivo/contratto.
11. Finanziamento al consumo (Cofidis/Compass/Findomestic).
12. Object storage S3 (già supportato via env).
13. Google Maps / geocoding cantieri e percorsi.
14. Telematica/route optimization (Routific, OptimoRoute).
15. CNC / software taglio (Emmegisoft, Orgadata LogiKal) export ordini/BOM.
16. Ottimizzazione vetro fornitori (ordini XML).
17. Recensioni Google Business / Trustpilot.
18. SMS OTP (Twilio) in alternativa email.
19. PEC provider per invio contratti.
20. Business intelligence esterna (Metabase/Power BI) su viste read-only.

## TOP_20_DUPLICATION_OR_ARCHITECTURAL_RISKS
1. Tre+ motori pricing coesistenti (`pricing.py`, `pricing_v2.py`, `pricing_v3/`, `parametric_engine`, `commercial_perimeter`, `multi_category_pricing`, `pricing_hub` metodi) — P2 backlog già noto.
2. Doppia BOM: `parametric` BOM/recipes CPQ vs `production.py /boms`.
3. Doppio catalogo: `catalog.py` vs `product_catalog.py` vs `product_categories/products` multi-cat.
4. `ConfiguratorDialog.jsx` legacy conservato non referenziato.
5. Route legacy nascoste (`/pricelists`, `/parametric`, `/quote-structure`) ancora attive.
6. `ErpModulePages.jsx` generica: 11 moduli condividono un componente list/create → nessuna logica di dominio in UI.
7. `ops_workflow.py` monolite (47 endpoint: aree, gruppi, handoff, commissioni, dashboard, webhook, inbox, template, automazioni, consensi).
8. `treasury.py` 34 endpoint + `management_control.py` 24 con sovrapposizione payables/AP.
9. Alert modellati in 3 posti (TreasuryAlert, AICFOSuggestion, AICFOInsight) senza unificazione.
10. Module gating non applicato uniformemente (rischio entitlement bypass).
11. Nessun scheduler → logiche "scan" esposte come endpoint manuali.
12. Snapshot contratto: `site` + `site_address` duplicati nello stesso snapshot.
13. Chiavi snapshot cambiate nel tempo (`lines`→`economics.lines`, `totals`→`quote_totals`) — test legacy rotti, rischio consumer esterni.
14. `xdist` parallel test causano race (utente viewer cancellato, contatori clienti) → falsi negativi.
15. Rate limiter login condiviso da test suite → 429 spurii.
16. Frontend pagine grandi (`QuoteEditorPage`, `TreasuryCFOPage` 730 righe) → manutenzione.
17. `WHATSAPP_PROVIDER`/`EMAIL_PROVIDER` mock di default: rischio deploy con mock in prod (mitigato da `configuration_required`).
18. `OTP_DEBUG_ENABLED` dipende da `APP_ENV` corretto in prod.
19. Permessi molto granulari (247) senza matrice ruolo-permesso documentata fuori dal seed.
20. Nessuna API pubblica versionata / contratto OpenAPI congelato per integratori.

---

## ROADMAP RACCOMANDATA (nessuna implementazione ora)
**P0 — Fondamenta trasversali (abilitano tutto il resto)**
- Scheduler piattaforma (`.emergent/crons.yml`) per: SLA lead/handoff, reminder appuntamenti, alert tesoreria, automazioni email, stale opportunity.
- Control Tower engine unico: `risks` collection (code, severity, impact €, owner, entity_ref, suggested_action, task_id) + generatori per i rischi già rilevabili (margin, discount, presign, variance, min_stock, receivables overdue, cash gap).
- Deploy + SMTP live + S3 + Redis prod (già pronti, solo config).

**P1 — Golden thread chiuso sull'operativo**
- Customer 360 aggregato (ordini/pagamenti/posa/ticket) + credit status.
- AR/AP aging + DSO/DPO + forecast cassa 4/8/13 settimane da scadenziario reale.
- Riserve materiali per commessa + stockout warning.
- Job costing actual (ore posa, consumo materiali) → profitability planned vs actual.
- Change order economico post-firma con approvazione cliente (riuso link pubblico + OTP).
- Asset installati + garanzia + SLA ticket.
- Mobile work order posa (checklist, foto, firma accettazione).
- Lead scoring semplice + routing regole + SLA prima risposta.
- Google Sign-in (msg 368) + MFA TOTP.

**P2 — Profondità moduli**
- Procurement: RFQ, requisition/approvazione, 3-way match, performance fornitori.
- Produzione: capacità/work center, scheduling finito semplice, shop-floor UI.
- Logistica: tracking, POD, percorsi (integrazione maps).
- FP&A: rolling forecast, forecast vs actual, P&L riclassificato, module gating uniforme.
- FEA/FEQ provider, WhatsApp Business, Meta Lead Ads.
- Consolidamento motori pricing e cataloghi duplicati.

**P3 — Estensioni**
- HR (presenze, skills, ferie) con paghe esterne; territori; referral/review/NPS; lotti/seriali/barcode; CNC/glass optimizer; public API.

**P4 — Visione**
- AI copilot per commerciale/CFO su dati reali; marketplace integrazioni; benchmark multi-tenant anonimo.

**HARD STOP — nessuna implementazione avviata.**
