import React, { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AuthLayout from "@/layouts/AuthLayout";
import { api, formatApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function AcceptInvitation() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [token, setToken] = useState(params.get("token") || "");
  const [first, setFirst] = useState(""); const [last, setLast] = useState("");
  const [p1, setP1] = useState(""); const [p2, setP2] = useState("");
  const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    if (p1.length < 8) return setErr(t("auth.password_min"));
    if (p1 !== p2) return setErr(t("auth.passwords_dont_match"));
    setLoading(true);
    try {
      await api.post("/auth/accept-invitation", { token, password: p1, first_name: first || null, last_name: last || null });
      navigate("/login?accepted=1");
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setLoading(false); }
  };

  return (
    <AuthLayout title={t("auth.accept_invitation")} subtitle={t("auth.accept_invitation_subtitle")} testId="accept-invitation-page">
      <form onSubmit={submit} className="space-y-5" data-testid="accept-invitation-form">
        {err && <Alert variant="destructive" className="rounded-sm"><AlertDescription>{err}</AlertDescription></Alert>}
        <div className="space-y-2">
          <Label className="overline">Token invito</Label>
          <Input value={token} onChange={(e) => setToken(e.target.value)} required
            className="rounded-sm h-11 font-mono-plex" data-testid="invite-token-input" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label className="overline">{t("auth.first_name")}</Label>
            <Input value={first} onChange={(e) => setFirst(e.target.value)} className="rounded-sm h-11" data-testid="invite-first-input" />
          </div>
          <div className="space-y-2">
            <Label className="overline">{t("auth.last_name")}</Label>
            <Input value={last} onChange={(e) => setLast(e.target.value)} className="rounded-sm h-11" data-testid="invite-last-input" />
          </div>
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.new_password")}</Label>
          <Input type="password" value={p1} onChange={(e) => setP1(e.target.value)} required
            className="rounded-sm h-11" data-testid="invite-p1-input" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.confirm_password")}</Label>
          <Input type="password" value={p2} onChange={(e) => setP2(e.target.value)} required
            className="rounded-sm h-11" data-testid="invite-p2-input" />
        </div>
        <Button type="submit" disabled={loading} className="w-full h-11 rounded-sm" data-testid="invite-submit-button">
          {loading ? t("common.loading") : t("auth.set_password")}
        </Button>
      </form>
    </AuthLayout>
  );
}
