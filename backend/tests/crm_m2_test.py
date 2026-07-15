"""Backend tests for Infissi Express Cloud M2 (CRM).

Covers: onboarding wizard, pipelines, leads CRUD + kanban + convert, customers,
contacts, activities (timeline + comms: call/email/whatsapp), tasks, appointments,
goals, role-specific dashboards, extended global search.

Ordered class-based flow: pytest-xdist loadscope pins each class to one worker.
"""
from __future__ import annotations
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    except Exception:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

ADMIN_EMAIL = "admin@infissiexpress.com"
ADMIN_PASSWORD = "Admin!2025"


def api(path: str) -> str:
    return f"{BASE_URL}/api{path}"


def _login_admin() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    r = sess.post(api("/auth/login"), json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    body = r.json()
    sess.headers.update({"Authorization": f"Bearer {body['access_token']}"})
    sess.user = body["user"]  # type: ignore[attr-defined]
    return sess


@pytest.fixture(scope="module")
def s() -> requests.Session:
    return _login_admin()


# =========================================================
# Dashboard variant
# =========================================================
class TestDashboardVariant:
    def test_variant_direction_for_superadmin(self, s):
        r = s.get(api("/dashboard-crm/variant"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["variant"] == "direction", data
        assert data["is_admin"] is True

    def test_direction_dashboard_shape(self, s):
        r = s.get(api("/dashboard-crm/direction"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["variant"] == "direction"
        assert "counters" in data
        for key in ("total_leads", "open_leads", "customers_total", "won_month",
                    "lost_month", "conversion_rate_month", "activities_7d",
                    "open_pipeline_value", "weighted_pipeline_value"):
            assert key in data["counters"], f"missing counter {key}"
        assert "top_performers" in data and isinstance(data["top_performers"], list)
        assert "stage_breakdown" in data and isinstance(data["stage_breakdown"], list)

    def test_sales_dashboard_shape(self, s):
        r = s.get(api("/dashboard-crm/sales"))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["variant"] == "sales"
        assert "counters" in d
        for k in ("leads_open", "leads_won_month", "appointments_today",
                  "tasks_open", "tasks_overdue", "weighted_pipeline_value",
                  "potential_pipeline_value"):
            assert k in d["counters"]
        assert "goals" in d and isinstance(d["goals"], list)
        assert "next_actions" in d and isinstance(d["next_actions"], list)


# =========================================================
# Onboarding
# =========================================================
class TestOnboarding:
    def test_get_state(self, s):
        r = s.get(api("/onboarding/state"))
        assert r.status_code == 200, r.text
        st = r.json()["state"]
        assert "step" in st
        assert "completed" in st

    def test_step_company(self, s):
        r = s.post(api("/onboarding/step-company"), json={
            "name": "Infissi Express Test", "vat_number": "IT12345678901",
            "city": "Milano", "phone": "0212345",
        })
        assert r.status_code == 200, r.text
        assert r.json()["next_step"] == 1

    def test_step_logo_nullable(self, s):
        r = s.post(api("/onboarding/step-logo"), json={"logo_url": None})
        assert r.status_code == 200, r.text
        assert r.json()["next_step"] == 2

    def test_step_sequences(self, s):
        r = s.post(api("/onboarding/step-sequences"), json={
            "quote_prefix": "PRV-", "quote_padding": 5,
            "order_prefix": "ORD-", "order_padding": 5, "year_reset": True,
        })
        assert r.status_code == 200, r.text
        assert r.json()["next_step"] == 3

    def test_step_invite(self, s):
        email = f"TEST_onb_{uuid.uuid4().hex[:6]}@infissiexpress.com"
        r = s.post(api("/onboarding/step-invite"), json={
            "email": email, "first_name": "Onb", "last_name": "Test", "role_slug": "commerciale",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["next_step"] == 4
        assert data.get("invitation_url")

    def test_step_first_lead(self, s):
        r = s.post(api("/onboarding/step-first-lead"), json={
            "first_name": "Mario", "last_name": "OnboardingTest",
            "email": "mario.onboarding@test.com", "estimated_value": 5000.0,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["next_step"] == 5
        assert data.get("lead_id")
        # verify activity lead_created recorded
        time.sleep(0.2)
        r2 = s.get(api(f"/activities?lead_id={data['lead_id']}"))
        assert r2.status_code == 200
        types = [a["type"] for a in r2.json()["items"]]
        assert "lead_created" in types

    def test_complete(self, s):
        r = s.post(api("/onboarding/complete"))
        assert r.status_code == 200
        r2 = s.get(api("/onboarding/state"))
        assert r2.json()["state"]["completed"] is True


# =========================================================
# Pipelines
# =========================================================
class TestPipelines:
    def test_default_pipeline_has_7_stages(self, s):
        r = s.get(api("/pipelines/default"))
        assert r.status_code == 200, r.text
        pipe = r.json()
        stages = pipe.get("stages") or []
        names = [s["name"] for s in stages]
        assert len(stages) == 7, f"expected 7 stages, got {len(stages)}: {names}"
        assert names[0] == "Nuovo"
        assert names[-1] == "Perso"
        assert any(s["is_won"] for s in stages)
        assert any(s["is_lost"] for s in stages)

    def test_create_custom_pipeline(self, s):
        r = s.post(api("/pipelines"), json={
            "name": f"TEST_Pipe_{uuid.uuid4().hex[:6]}",
            "description": "test pipeline",
        })
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["name"].startswith("TEST_Pipe_")
        assert len(p.get("stages", [])) == 7


# =========================================================
# Leads CRUD + Kanban + Convert
# =========================================================
class TestLeads:
    LEAD_STATE: dict = {}

    def test_create_lead(self, s):
        r = s.post(api("/leads"), json={
            "first_name": "Mario", "last_name": "Rossi",
            "email": "mario.rossi@test.com", "phone": "3331112222",
            "source": "website", "estimated_value": 12500.0,
            "tags": ["TEST"], "notes": "Interested in windows",
        })
        assert r.status_code == 200, r.text
        lead = r.json()
        assert lead["first_name"] == "Mario"
        assert lead["probability"] == 10  # first stage "Nuovo" default
        assert lead["pipeline_id"] and lead["stage_id"]
        TestLeads.LEAD_STATE["lead_id"] = lead["id"]
        TestLeads.LEAD_STATE["stage_id"] = lead["stage_id"]
        TestLeads.LEAD_STATE["pipeline_id"] = lead["pipeline_id"]
        # activity recorded
        time.sleep(0.2)
        r2 = s.get(api(f"/activities?lead_id={lead['id']}"))
        assert r2.status_code == 200
        types = [a["type"] for a in r2.json()["items"]]
        assert "lead_created" in types

    def test_list_leads_with_intelligence(self, s):
        r = s.get(api("/leads"))
        assert r.status_code == 200
        items = r.json()["items"]
        mine = next((l for l in items if l["id"] == TestLeads.LEAD_STATE["lead_id"]), None)
        assert mine, "created lead not in list"
        intel = mine.get("intelligence")
        assert intel, "intelligence not attached to lead"
        assert "next_action_suggestion" in intel
        assert "probability_display" in intel
        assert "days_since_contact" in intel

    def test_kanban(self, s):
        r = s.get(api("/leads/kanban"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "pipeline" in data and "columns" in data
        cols = data["columns"]
        assert len(cols) == 7
        # find lead in any column
        found = False
        for c in cols:
            for l in c["leads"]:
                if l["id"] == TestLeads.LEAD_STATE["lead_id"]:
                    found = True
                    assert "intelligence" in l
                    break
        assert found, "created lead missing from kanban"

    def test_stage_change_records_activity(self, s):
        # Get default pipeline stages, pick a different one (Contattato = order 1)
        pipe = s.get(api("/pipelines/default")).json()
        contattato = next(st for st in pipe["stages"] if st["name"] == "Contattato")
        vinto = next(st for st in pipe["stages"] if st["name"] == "Vinto")

        lid = TestLeads.LEAD_STATE["lead_id"]
        r = s.patch(api(f"/leads/{lid}"), json={"stage_id": contattato["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["stage_id"] == contattato["id"]
        # activity recorded
        r2 = s.get(api(f"/activities?lead_id={lid}&type=stage_changed"))
        assert r2.status_code == 200
        assert len(r2.json()["items"]) >= 1

        # Move to Vinto -> won_at set
        r3 = s.patch(api(f"/leads/{lid}"), json={"stage_id": vinto["id"]})
        assert r3.status_code == 200
        assert r3.json().get("won_at"), "won_at should be set when moving to won stage"

    def test_convert_lead(self, s):
        # Create a fresh lead to convert (avoid conflict with previous won-stage lead)
        r = s.post(api("/leads"), json={
            "first_name": "TEST_Conv", "last_name": "Lead", "email": "conv@test.com",
        })
        assert r.status_code == 200
        lid = r.json()["id"]
        r2 = s.post(api(f"/leads/{lid}/convert"), json={"customer_type": "private"})
        assert r2.status_code == 200, r2.text
        cust = r2.json()
        assert cust["id"]
        assert cust["origin_lead_id"] == lid
        TestLeads.LEAD_STATE["converted_customer_id"] = cust["id"]
        TestLeads.LEAD_STATE["converted_lead_id"] = lid
        # lead now has customer_id and conversion activity
        lead = s.get(api(f"/leads/{lid}")).json()
        assert lead["customer_id"] == cust["id"]
        acts = s.get(api(f"/activities?lead_id={lid}&type=conversion")).json()["items"]
        assert len(acts) >= 1

    def test_soft_delete_lead(self, s):
        # Create and delete
        r = s.post(api("/leads"), json={"first_name": "TEST_ToDelete", "last_name": "X"})
        lid = r.json()["id"]
        r2 = s.delete(api(f"/leads/{lid}"))
        assert r2.status_code == 200
        r3 = s.get(api(f"/leads/{lid}"))
        assert r3.status_code == 404


# =========================================================
# Customers
# =========================================================
class TestCustomers:
    STATE: dict = {}

    def test_crud(self, s):
        # create
        r = s.post(api("/customers"), json={
            "first_name": "TEST_Cliente", "last_name": "One",
            "email": "cliente@test.com", "customer_type": "private",
        })
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        TestCustomers.STATE["cid"] = cid
        # list
        r2 = s.get(api("/customers"))
        assert any(c["id"] == cid for c in r2.json()["items"])
        # patch
        r3 = s.patch(api(f"/customers/{cid}"), json={"phone": "3339998888"})
        assert r3.status_code == 200
        assert r3.json()["phone"] == "3339998888"
        # delete
        r4 = s.delete(api(f"/customers/{cid}"))
        assert r4.status_code == 200
        # 404 after delete
        r5 = s.get(api(f"/customers/{cid}"))
        assert r5.status_code == 404


# =========================================================
# Contacts
# =========================================================
class TestContacts:
    def test_contact_linked_to_lead(self, s):
        # create a lead first
        r = s.post(api("/leads"), json={"first_name": "TEST_ContactLead", "last_name": "X"})
        lid = r.json()["id"]
        # create contact linked to lead
        r2 = s.post(api("/contacts"), json={
            "first_name": "TEST_Contact", "last_name": "One", "role": "Owner",
            "email": "contact@test.com", "lead_id": lid,
        })
        assert r2.status_code == 200, r2.text
        cid = r2.json()["id"]
        # list filtered
        r3 = s.get(api(f"/contacts?lead_id={lid}"))
        assert r3.status_code == 200
        assert any(c["id"] == cid for c in r3.json()["items"])
        # patch
        r4 = s.patch(api(f"/contacts/{cid}"), json={"role": "CEO"})
        assert r4.status_code == 200
        assert r4.json()["role"] == "CEO"
        # delete
        r5 = s.delete(api(f"/contacts/{cid}"))
        assert r5.status_code == 200


# =========================================================
# Activities + Comms
# =========================================================
class TestActivitiesAndComms:
    STATE: dict = {}

    def test_setup_lead(self, s):
        r = s.post(api("/leads"), json={
            "first_name": "TEST_Acts", "last_name": "Timeline",
            "email": "acts@test.com", "phone": "3339990000",
        })
        assert r.status_code == 200
        TestActivitiesAndComms.STATE["lid"] = r.json()["id"]

    def test_create_manual_note(self, s):
        lid = TestActivitiesAndComms.STATE["lid"]
        r = s.post(api("/activities"), json={
            "type": "note", "subject": "Manual note",
            "body": "Discussed via note", "lead_id": lid,
        })
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "note"
        # last_activity_at bumped
        lead = s.get(api(f"/leads/{lid}")).json()
        assert lead.get("last_activity_at"), "last_activity_at should be bumped"

    def test_log_call(self, s):
        lid = TestActivitiesAndComms.STATE["lid"]
        r = s.post(api("/activities/log-call"), json={
            "to": "3339990000", "direction": "out", "outcome": "answered",
            "duration_seconds": 120, "subject": "Test Call",
            "notes": "Called client", "lead_id": lid,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "call"
        assert d["direction"] == "out"
        assert d["duration_seconds"] == 120
        # last_contact_at bumped
        lead = s.get(api(f"/leads/{lid}")).json()
        assert lead.get("last_contact_at")

    def test_send_email_mock(self, s):
        lid = TestActivitiesAndComms.STATE["lid"]
        r = s.post(api("/activities/send-email"), json={
            "to": "test@example.com", "subject": "Test Email",
            "body": "Hello from test", "lead_id": lid,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["activity"]["type"] == "email"
        assert d.get("email_log_id")

    def test_send_whatsapp_mock(self, s):
        lid = TestActivitiesAndComms.STATE["lid"]
        r = s.post(api("/activities/send-whatsapp"), json={
            "to": "+391112223333", "body": "Ciao WhatsApp test", "lead_id": lid,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["activity"]["type"] == "whatsapp"
        assert d["whatsapp"]["status"] == "sent"
        assert d["whatsapp"].get("provider_message_id")

    def test_whatsapp_logs(self, s):
        r = s.get(api("/activities/whatsapp-logs"))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert items[0]["status"] in ("sent", "queued")

    def test_timeline_returns_all_events(self, s):
        lid = TestActivitiesAndComms.STATE["lid"]
        r = s.get(api(f"/activities?lead_id={lid}"))
        assert r.status_code == 200
        types = {a["type"] for a in r.json()["items"]}
        # Should include lead_created + note + call + email + whatsapp
        for t in ("lead_created", "note", "call", "email", "whatsapp"):
            assert t in types, f"missing {t} in timeline: {types}"


# =========================================================
# Tasks
# =========================================================
class TestTasks:
    STATE: dict = {}

    def test_create_task(self, s):
        r = s.post(api("/tasks"), json={
            "title": "TEST_Task Follow up",
            "description": "Follow up client",
            "priority": "high",
        })
        assert r.status_code == 200, r.text
        TestTasks.STATE["tid"] = r.json()["id"]

    def test_list_mine(self, s):
        r = s.get(api("/tasks?mine=true"))
        assert r.status_code == 200
        assert any(t["id"] == TestTasks.STATE["tid"] for t in r.json()["items"])

    def test_mark_done_records_activity(self, s):
        tid = TestTasks.STATE["tid"]
        r = s.patch(api(f"/tasks/{tid}"), json={"task_status": "done"})
        assert r.status_code == 200
        d = r.json()
        assert d["task_status"] == "done"
        assert d.get("completed_at")

    def test_delete_task(self, s):
        r = s.delete(api(f"/tasks/{TestTasks.STATE['tid']}"))
        assert r.status_code == 200


# =========================================================
# Appointments
# =========================================================
class TestAppointments:
    STATE: dict = {}

    def test_create_appointment(self, s):
        now = datetime.now(timezone.utc)
        start = (now + timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=2)).isoformat()
        r = s.post(api("/appointments"), json={
            "title": "TEST_Appointment", "start_at": start, "end_at": end,
            "location": "Client site", "appointment_type": "meeting",
        })
        assert r.status_code == 200, r.text
        TestAppointments.STATE["aid"] = r.json()["id"]

    def test_list(self, s):
        r = s.get(api("/appointments"))
        assert r.status_code == 200
        assert any(a["id"] == TestAppointments.STATE["aid"] for a in r.json()["items"])

    def test_mark_done_records_activity(self, s):
        aid = TestAppointments.STATE["aid"]
        r = s.patch(api(f"/appointments/{aid}"), json={"appointment_status": "done"})
        assert r.status_code == 200
        assert r.json()["appointment_status"] == "done"

    def test_delete(self, s):
        r = s.delete(api(f"/appointments/{TestAppointments.STATE['aid']}"))
        assert r.status_code == 200


# =========================================================
# Goals
# =========================================================
class TestGoals:
    def test_create_and_list_goal(self, s):
        now = datetime.now(timezone.utc)
        r = s.post(api("/goals"), json={
            "user_id": s.user["id"],  # type: ignore[attr-defined]
            "period_type": "month",
            "period_start": now.replace(day=1).isoformat(),
            "period_end": (now.replace(day=28) + timedelta(days=5)).isoformat(),
            "metric": "revenue",
            "target_value": 50000.0,
        })
        assert r.status_code == 200, r.text
        gid = r.json()["id"]
        r2 = s.get(api("/goals?mine=true"))
        assert r2.status_code == 200
        assert any(g["id"] == gid for g in r2.json()["items"])
        # patch
        r3 = s.patch(api(f"/goals/{gid}"), json={"achieved_value": 10000.0})
        assert r3.status_code == 200
        assert r3.json()["achieved_value"] == 10000.0


# =========================================================
# Extended Global Search
# =========================================================
class TestGlobalSearch:
    def test_search_finds_lead(self, s):
        # create a lead with a unique searchable name
        uniq = uuid.uuid4().hex[:6]
        name = f"Ricercabile{uniq}"
        r = s.post(api("/leads"), json={"first_name": name, "last_name": "Search"})
        assert r.status_code == 200
        lid = r.json()["id"]
        r2 = s.get(api(f"/search?q={name}"))
        assert r2.status_code == 200, r2.text
        results = r2.json()["results"]
        found = next((x for x in results if x["collection"] == "leads" and x["id"] == lid), None)
        assert found, f"Lead not found in global search: {results}"
        assert found["link"] == f"/leads/{lid}"
