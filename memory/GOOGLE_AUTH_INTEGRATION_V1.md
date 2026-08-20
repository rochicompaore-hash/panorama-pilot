# GOOGLE AUTH INTEGRATION V1 — Enerhia Operating Core

**Data:** 2026-02-19 · **Branch:** `feature/enerhia-operating-core-v1`
**Stato:** **BLUEPRINT_READY_FOR_IMPLEMENTATION** — playbook Emergent Auth acquisito, decisioni policy definitive.
**Implementazione codice:** rinviata alla prossima iterazione (context limits questo turno).

## Configurazione approvata: 1c + 2a + 3c + 4a + 5a

| # | Scelta | Regola |
|---|---|---|
| 1c | Nessun tenant auto | Nuovi utenti Google → `tenant_id=null`, `account_status=PENDING_TENANT_ASSIGNMENT` |
| 2a | Nessun ruolo default | `roles=[]`, `permissions=[]` — Super Admin assegna manualmente |
| 3c | Allowlist manuale | Collection `google_auth_allowlist` — solo email autorizzate esplicitamente |
| 4a | Coesistenza | Bottone "Accedi con Google" AGGIUNTO alla LoginPage esistente (email/password rimane) |
| 5a | Account linking | Se `google_verified_email == existing_user.email` (exact match) → stesso `user_id` |

## Architettura (Emergent Auth playbook)

```
LoginPage
  │
  ├─► email/password (JWT esistente — invariato)
  │
  └─► "Accedi con Google" button
        │  redirect a  https://auth.emergentagent.com/?redirect={window.location.origin}/auth-callback
        ▼
     Google OAuth (Emergent-managed)
        │  ritorno: {redirect}#session_id={sid}
        ▼
     Frontend /auth-callback (nuovo)
        │  POST /api/auth/google/callback  {session_id}
        ▼
     Backend endpoint (nuovo)
        │  1. GET https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data
        │       header: X-Session-ID
        │  2. Valida email vs google_auth_allowlist (deny → GOOGLE_LOGIN_DENIED_NOT_ALLOWLISTED)
        │  3. Existing user with email? → link (§5-§9) → return JWT esistente
        │  4. Not existing? → create user con tenant_id=null, PENDING_TENANT_ASSIGNMENT
        │  5. Salva session_token httpOnly cookie (7gg) + emette JWT app
        ▼
     Redirect a /dashboard (se attivo) o /pending-account (se PENDING)
```

## Nuove collection MongoDB (blueprint)

**`google_auth_allowlist`** (tenant-agnostic, gestita da Super Admin platform-level):
```
{ _id, email (normalized: trim+lowercase, unique), added_by_user_id, added_at,
  active: bool, note: str, deactivated_at: nullable }
```

**`user_auth_identities`** (§8-§9):
```
{ _id, user_id, provider: "PASSWORD"|"GOOGLE", provider_subject: google_sub,
  provider_email, created_at, last_used_at }
```

**Users collection — nuovi campi**:
```
account_status: "ACTIVE" | "PENDING_TENANT_ASSIGNMENT" | "SUSPENDED"
tenant_id: nullable   # era sempre valorizzato, ora nullable per pending
```

## Nuovi endpoint backend

| Endpoint | Note |
|---|---|
| `POST /api/auth/google/callback` | Riceve `session_id`, chiama Emergent, gestisce linking/creazione, emette JWT |
| `GET /api/admin/pending-users` | Super Admin: lista utenti PENDING_TENANT_ASSIGNMENT |
| `POST /api/admin/users/{id}/assign-tenant` | Body: `{tenant_id, role_ids[]}` — attiva l'utente |
| `GET /api/admin/google-auth-allowlist` | Lista whitelist |
| `POST /api/admin/google-auth-allowlist` | Aggiungi email |
| `DELETE /api/admin/google-auth-allowlist/{id}` | Rimuovi |
| `PATCH /api/admin/google-auth-allowlist/{id}` | Attiva/disattiva |

## Middleware guard per PENDING users (§11)

Nel dependency `require_permission`, se `user.account_status == PENDING_TENANT_ASSIGNMENT`:
- Consenti solo: `/api/auth/me`, `/api/auth/logout`, `/api/pending-account/*`
- Nega tutto il resto con `403 TENANT_ASSIGNMENT_REQUIRED`

## Frontend

- **LoginPage** (esistente): aggiungere sotto il form una sezione "─ oppure ─" + `<Button data-testid="google-login-button">Accedi con Google</Button>`
- **AppRouter**: `if (location.hash?.includes('session_id=')) return <AuthCallback />;`
- **AuthCallback** (nuovo): `useRef` per idempotenza · POST callback · redirect a `/dashboard` o `/pending-account`
- **PendingAccountPage** (nuovo): "Account creato. In attesa di abilitazione."
- **AuthContext**: skip `/auth/me` check se `window.location.hash?.includes('session_id=')` (playbook §4)

## Regole di sicurezza rispettate

- ✅ Email normalizzate (trim + lowercase) prima di lookup allowlist e user linking
- ✅ Linking automatico SOLO se `verified_email==true` da Google + exact match + user attivo
- ✅ Provider subject (`google_sub`) salvato per future validazioni (non solo email)
- ✅ Tenant isolation invariata: Google auth non modifica `tenant_id`/`role_ids` di utenti esistenti
- ✅ RBAC identico per PASSWORD e GOOGLE identity (§14)
- ✅ Nessun tenant auto-created da dominio (§19)
- ✅ Cliente esterno NON gestito qui (§20)

## Audit events (§13)

Tabella `audit_events` (esistente):
- `GOOGLE_LOGIN_SUCCESS` (email, user_id, was_new: bool, was_linked: bool)
- `GOOGLE_LOGIN_DENIED_NOT_ALLOWLISTED` (email)
- `GOOGLE_IDENTITY_LINKED` (user_id, google_sub)
- `NEW_GOOGLE_USER_CREATED` (email, user_id)
- `USER_PENDING_TENANT` (user_id)
- `TENANT_ASSIGNED` (user_id, tenant_id, assigned_by)
- `ROLE_ASSIGNED` (user_id, role_ids, assigned_by)

## Test plan (§14-§18)

1. **Staff linking**: user X esiste con email/password → login Google con stessa verified email → user_id identico, tenant/role/permissions immutati
2. **Nuovo whitelist**: email in allowlist, no user → create PENDING, deny business API
3. **No whitelist**: email non in allowlist → deny + no user creato
4. **Multi-tenant**: user tenant A non vede dati tenant B nemmeno con URL manipulation
5. **RBAC parity**: stesso utente identico permessi via PASSWORD o GOOGLE

## STOP (§26)

Dopo l'implementazione Google Auth: **NESSUNA nuova feature**. Solo audit generale.
