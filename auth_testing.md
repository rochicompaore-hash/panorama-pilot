# Auth testing playbook (Emergent Google OAuth) — adattato a Panorama
L'app usa il proprio JWT: `POST /api/auth/google/session {session_id}` scambia il session_id Emergent e restituisce `access_token` (bearer) + cookie `access_token`/`refresh_token`/`session_token`.
Il session_id reale non è simulabile offline: testare (1) UI bottone `login-google-btn` → redirect a https://auth.emergentagent.com/?redirect=<origin>/ ; (2) callback `/#session_id=fake` → schermata `auth-callback` → backend 401 → ritorno a /login con errore visibile; (3) fail-closed 403 GOOGLE_ACCOUNT_NOT_LINKED è verificabile solo con session_id valido (account non collegato).
Account collegato: rochicompaore@gmail.com → admin@infissiexpress.com. Credenziali password classiche in /app/memory/test_credentials.md.
