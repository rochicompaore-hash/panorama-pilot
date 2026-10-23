"""Generate private review scenarios through the actual cash-command-center service.

All records below are synthetic. FixtureDB supplies read-only data in memory; it
does not replace financial functions, open sockets, load .env, or contact MongoDB.
The browser consumes the resulting snapshots and performs no cash calculations.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.cash_engine import command_center  # noqa: E402

TODAY = date(2026, 10, 23)
TENANT = "synthetic-cash-preview"
ENTITY = "PREVIEW"


def value_at(document, key):
    value = document
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def matches(document, query):
    """Only the read filters used by these scenarios; unknown operators fail closed."""
    for key, wanted in (query or {}).items():
        actual = value_at(document, key)
        if isinstance(wanted, dict):
            for op, operand in wanted.items():
                if op == "$ne":
                    ok = actual != operand
                elif op == "$in":
                    ok = actual in operand
                elif op == "$nin":
                    ok = actual not in operand
                else:
                    raise ValueError(f"Unsupported fixture query operator: {op}")
                if not ok:
                    return False
        elif actual != wanted:
            return False
    return True


class FixtureCursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    async def to_list(self, length):
        return self.rows[:length]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


class FixtureCollection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query=None, projection=None):
        # Extra fields are harmless for read-only engine consumers. All filters
        # are applied, including paid/open payables that share one collection.
        return FixtureCursor([row for row in self.rows if matches(row, query)])

    async def find_one(self, query=None, projection=None, sort=None):
        rows = await self.find(query, projection).to_list(10000)
        if sort:
            for key, direction in reversed(sort):
                rows.sort(key=lambda row: value_at(row, key), reverse=direction < 0)
        return rows[0] if rows else None


class FixtureDB:
    def __init__(self, records):
        self.records = records

    def __getattr__(self, name):
        return FixtureCollection(self.records.get(name, []))

    def __getitem__(self, name):
        return getattr(self, name)


def dated(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def record(key, **fields):
    return {"_id": key, "tenant_id": TENANT, "legal_entity_id": ENTITY,
            "deleted_at": None, **fields}


def new_records(certified=True):
    account = record("demo-bank", label="Conto di prova", bank_name="Banca dimostrativa", active=True)
    if certified:
        account.update(certified_balance=3000, certified_at=dated(0))
    return {"bank_accounts": [account], "contracts": [], "payment_plans": [],
            "customers": [], "sales_orders": [], "payables": [],
            "cfo_settings": [record(f"{TENANT}:{ENTITY}", minimum_cash_reserve=1000)]}


def add_receivable(records, key, amount, due=None, *, trigger=None, disputed=False,
                   order_status="in_production", event_date=None, expected=None):
    customer_id, contract_id, plan_id = f"customer-{key}", f"contract-{key}", f"plan-{key}"
    records["customers"].append(record(customer_id, name=f"Cliente dimostrativo {key.upper()}"))
    records["contracts"].append(record(contract_id, customer_id=customer_id,
        contract_status="signed", signed_at=dated(-35), number=f"DEMO-{key.upper()}",
        economic_snapshot={"total": amount, "subtotal": round(amount / 1.22, 2)}))
    installment = {"ref": "saldo", "label": "Saldo di prova", "amount": amount,
                   "paid_amount": 0, "installment_status": "disputed" if disputed else "pending"}
    if due is not None:
        installment["due_date"] = due
    if trigger:
        installment["trigger"] = trigger
    records["payment_plans"].append(record(plan_id, contract_id=contract_id,
        customer_id=customer_id, total_amount=amount, installments=[installment]))
    if trigger:
        order = record(f"order-{key}", contract_id=contract_id, number=f"ORD-{key.upper()}",
                       order_status=order_status, updated_at=dated(0))
        if event_date:
            order["goods_ready_at"] = event_date
        if expected:
            order["expected_ready_date"] = expected
        records["sales_orders"].append(order)


def add_payable(records, key, amount, offset, category="FORNITORI"):
    records["payables"].append(record(f"payable-{key}", label=f"Uscita di prova {key}",
        creditor="Fornitore dimostrativo", amount_gross=amount, amount_paid=0,
        residual=amount, payable_status="pending", due_date=dated(offset), category=category))


def scenario_inputs():
    overdue = new_records()
    add_receivable(overdue, "scaduto", 18000, dated(-10))
    add_receivable(overdue, "pianificato", 5000, dated(5))
    add_receivable(overdue, "merce-attesa", 4000, trigger="goods_ready", expected=dated(10))
    add_payable(overdue, "stipendi", 4000, 3, "STIPENDI")
    add_payable(overdue, "fornitore", 6000, 15)

    uncertified = copy.deepcopy(overdue)
    uncertified["bank_accounts"] = new_records(certified=False)["bank_accounts"]

    undated = new_records()
    add_receivable(undated, "senza-data", 7000)
    add_receivable(undated, "data-invalida", 2500, "data-da-confermare")
    add_receivable(undated, "merce-pronta", 4000, trigger="goods_ready", order_status="completed")
    add_receivable(undated, "contestato", 2000, dated(2), disputed=True)
    add_receivable(undated, "pianificato", 1000, dated(6))
    add_payable(undated, "scaduta", 1500, -3)
    add_payable(undated, "prossima", 1500, 6)

    boundary = new_records()
    add_receivable(boundary, "oggi", 500, dated(0))
    add_receivable(boundary, "giorno-90", 6000, dated(90))
    add_receivable(boundary, "giorno-91", 9000, dated(91))
    add_payable(boundary, "scaduta", 700, -5)
    add_payable(boundary, "giorno-90", 1000, 90)
    add_payable(boundary, "giorno-91", 2000, 91)

    return [
        ("overdue", "Scaduti da recuperare", "18.000 € scaduti restano visibili tra i crediti. La previsione a 30 giorni considera 5.000 € di incassi pianificati e 10.000 € di uscite.", overdue),
        ("uncertified", "Saldo non certificato", "Senza un saldo certificato, la cassa e il relativo grafico restano non disponibili. Crediti e scadenze sono comunque consultabili.", uncertified),
        ("undated", "Date da verificare", "Le rate senza data valida e la merce pronta senza una data dell'evento restano fuori previsione. I debiti scaduti sono considerati subito.", undated),
        ("boundary", "Tredici settimane", "La previsione comprende 91 date: oggi e i 90 giorni successivi. Le scadenze al giorno 91 restano fuori da questo intervallo.", boundary),
    ]


async def main():
    snapshots = []
    for key, title, description, records in scenario_inputs():
        data = await command_center(FixtureDB(records), TENANT, ENTITY, TODAY)
        snapshots.append({"id": key, "title": title, "description": description, "data": data})
    output = Path(__file__).parent / "data" / "scenarios.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n")
    provenance = {
        "synthetic_data": True,
        "as_of": TODAY.isoformat(),
        "generator": "preview/cashflow/generate_data.py",
        "entrypoint": "app.services.cash_engine.command_center",
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT / "backend/app/services/cash_engine.py", ROOT / "backend/app/services/cfo_engine.py"]},
        "scenarios": len(snapshots),
    }
    (output.parent / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Generated {len(snapshots)} synthetic scenarios through command_center: {output}")
    for scenario in snapshots:
        print(scenario["id"], json.dumps({
            "cash_today": scenario["data"]["situation_today"]["cash_today"],
            "projected_30d": scenario["data"]["horizons"]["30d"]["projected_cash"],
            "collections_30d": scenario["data"]["horizons"]["30d"]["expected_collections"],
        }))


if __name__ == "__main__":
    asyncio.run(main())
