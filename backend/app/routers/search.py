"""Global search across pilot collections + CRM entities."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from app.db import get_db
from app.deps import require_permission
from app.mongo_utils import from_mongo

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, le=50),
    user: dict = Depends(require_permission("search.global")),
):
    db = get_db()
    tenant = user["tenant_id"]
    rx = {"$regex": q, "$options": "i"}
    results: list[dict] = []

    # Leads
    leads = await db.leads.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"first_name": rx}, {"last_name": rx}, {"company_name": rx}, {"email": rx}, {"phone": rx}, {"whatsapp": rx}, {"tags": rx}, {"notes": rx}, {"address.city": rx}, {"address.street": rx}]}
    ).limit(limit).to_list(limit)
    for l in leads:
        name = f'{l.get("first_name","")} {l.get("last_name","")}'.strip() or l.get("company_name") or l.get("email") or "Lead"
        results.append({
            "collection": "leads", "type": "Lead", "id": l["_id"], "title": name,
            "subtitle": l.get("email") or l.get("phone") or l.get("company_name") or "",
            "link": f'/leads/{l["_id"]}',
        })

    # Customers
    customers = await db.customers.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"first_name": rx}, {"last_name": rx}, {"company_name": rx}, {"email": rx}, {"phone": rx}, {"whatsapp": rx}, {"vat_number": rx}, {"tags": rx}, {"address.city": rx}]}
    ).limit(limit).to_list(limit)
    for c in customers:
        name = f'{c.get("first_name","")} {c.get("last_name","")}'.strip() or c.get("company_name") or c.get("email") or "Cliente"
        results.append({
            "collection": "customers", "type": "Cliente", "id": c["_id"], "title": name,
            "subtitle": c.get("email") or c.get("phone") or c.get("company_name") or "",
            "link": f'/customers/{c["_id"]}',
        })

    # Contacts
    contacts = await db.contacts.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"first_name": rx}, {"last_name": rx}, {"email": rx}, {"phone": rx}, {"role": rx}]}
    ).limit(limit).to_list(limit)
    for c in contacts:
        name = f'{c.get("first_name","")} {c.get("last_name","")}'.strip()
        results.append({
            "collection": "contacts", "type": "Contatto", "id": c["_id"], "title": name,
            "subtitle": c.get("role") or c.get("email") or c.get("phone") or "",
            "link": "/contacts",
        })

    # Activities (calls/emails/whatsapp/notes)
    acts = await db.activities.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"subject": rx}, {"body": rx}]}
    ).sort("occurred_at", -1).limit(limit).to_list(limit)
    for a in acts:
        results.append({
            "collection": "activities", "type": a.get("type","Attività").title(),
            "id": a["_id"], "title": a.get("subject") or "",
            "subtitle": (a.get("body") or "")[:80],
            "link": f'/leads/{a["lead_id"]}' if a.get("lead_id") else (f'/customers/{a["customer_id"]}' if a.get("customer_id") else "/audit"),
        })

    # Tasks
    tasks = await db.tasks.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"title": rx}, {"description": rx}]}
    ).limit(limit).to_list(limit)
    for t in tasks:
        results.append({
            "collection": "tasks", "type": "Task", "id": t["_id"],
            "title": t.get("title"),
            "subtitle": t.get("description") or "",
            "link": "/tasks",
        })

    # Appointments
    appts = await db.appointments.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"title": rx}, {"description": rx}, {"location": rx}]}
    ).limit(limit).to_list(limit)
    for a in appts:
        results.append({
            "collection": "appointments", "type": "Appuntamento", "id": a["_id"],
            "title": a.get("title"),
            "subtitle": a.get("location") or "",
            "link": "/calendar",
        })

    # Users
    users = await db.users.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"email": rx}, {"first_name": rx}, {"last_name": rx}]}
    ).limit(limit).to_list(limit)
    for u in users:
        results.append({
            "collection": "users", "type": "Utente", "id": u["_id"],
            "title": f'{u.get("first_name","")} {u.get("last_name","")}'.strip() or u["email"],
            "subtitle": u["email"], "link": "/users",
        })

    # Attachments
    atts = await db.attachments.find(
        {"tenant_id": tenant, "deleted_at": None,
         "$or": [{"filename": rx}, {"description": rx}, {"tags": rx}]}
    ).limit(limit).to_list(limit)
    for a in atts:
        results.append({
            "collection": "attachments", "type": "Allegato", "id": a["_id"],
            "title": a.get("filename"), "subtitle": a.get("entity_type", ""),
            "link": "/attachments",
        })

    return {"query": q, "results": results, "total": len(results)}
