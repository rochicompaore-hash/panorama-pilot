import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Seo } from "@/seo/Seo";
import AuthLayout from "@/layouts/AuthLayout";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { API_BASE, formatApiError } from "@/api/client";

const STATUS_LABEL = {
  PENDING_EMAIL_VERIFICATION: { label: "In attesa di verifica email", text: "Controlla la tua casella email e conferma l'indirizzo per proseguire." },
  PENDING_APPROVAL: { label: "In attesa di approvazione", text: "Registrazione ricevuta. Il tuo account è in attesa di approvazione da parte dell'amministratore." },
  APPROVED: { label: "Approvato", text: "Il tuo account è stato approvato: puoi accedere." },
  REJECTED: { label: "Non approvato", text: "La richiesta non è stata approvata. Per informazioni contatta l'amministratore." },
  SUSPENDED: { label: "Sospeso", text: "Account sospeso. Contatta l'amministratore." },
};

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    const token = params.get("token");
    if (!token) { setState({ loading: false, error: "Link non valido." }); return; }
    axios.post(`${API_BASE}/auth/verify-email`, { token })
      .then((r) => { localStorage.setItem("registration_request_id", r.data.request_id); setState({ loading: false, data: r.data }); })
      .catch((e) => setState({ loading: false, error: formatApiError(e.response?.data?.detail) || e.message }));
  }, [params]);
  return (
    <AuthLayout title="Verifica email" testId="verify-email-page">
      <Seo title="Verifica email" path="/verify-email" />
      {state.loading && <p className="text-sm text-muted-foreground" data-testid="verify-loading">Verifica in corso…</p>}
      {state.error && <Alert variant="destructive" className="rounded-sm" data-testid="verify-error"><AlertDescription>{state.error}</AlertDescription></Alert>}
      {state.data && (
        <div className="space-y-4" data-testid="verify-success">
          <Alert className="rounded-sm"><AlertDescription>{state.data.message}</AlertDescription></Alert>
          <Button asChild className="rounded-sm" data-testid="verify-go-status"><Link to="/registration-status">Stato richiesta</Link></Button>
        </div>
      )}
    </AuthLayout>
  );
}

export default function RegistrationStatusPage() {
  const [state, setState] = useState({ loading: true });
  const reqId = localStorage.getItem("registration_request_id");
  useEffect(() => {
    if (!reqId) { setState({ loading: false, error: "Nessuna richiesta di registrazione trovata su questo dispositivo." }); return; }
    axios.get(`${API_BASE}/auth/registration/${reqId}`)
      .then((r) => setState({ loading: false, data: r.data }))
      .catch((e) => setState({ loading: false, error: formatApiError(e.response?.data?.detail) || e.message }));
  }, [reqId]);
  const info = state.data ? STATUS_LABEL[state.data.status] : null;
  return (
    <AuthLayout title="Stato della richiesta" subtitle="Puoi vedere solo lo stato della tua richiesta di registrazione." testId="registration-status-page">
      <Seo title="Stato richiesta" path="/registration-status" />
      {state.loading && <p className="text-sm text-muted-foreground">Caricamento…</p>}
      {state.error && <Alert variant="destructive" className="rounded-sm" data-testid="status-error"><AlertDescription>{state.error}</AlertDescription></Alert>}
      {state.data && (
        <div className="space-y-4" data-testid="registration-status-card">
          <div className="p-4 border border-border rounded-sm">
            <div className="overline">Stato</div>
            <div className="font-display text-xl font-black" data-testid="registration-status-value">{info?.label || state.data.status}</div>
            <p className="text-sm text-muted-foreground mt-2">{info?.text}</p>
            <div className="text-xs text-muted-foreground mt-3">Ruolo richiesto: <b>{state.data.requested_role}</b> · Email verificata: {state.data.email_verified ? "sì" : "no"}</div>
          </div>
          <Button asChild variant="outline" className="rounded-sm" data-testid="status-go-login"><Link to="/login">Vai al login</Link></Button>
        </div>
      )}
    </AuthLayout>
  );
}
