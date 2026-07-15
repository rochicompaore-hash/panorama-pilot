import React, { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AuthLayout from "@/layouts/AuthLayout";
import { api, formatApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function ResetPassword() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [token, setToken] = useState(params.get("token") || "");
  const [p1, setP1] = useState(""); const [p2, setP2] = useState("");
  const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    if (p1.length < 8) return setErr(t("auth.password_min"));
    if (p1 !== p2) return setErr(t("auth.passwords_dont_match"));
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: p1 });
      navigate("/login?reset=1");
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setLoading(false); }
  };

  return (
    <AuthLayout title={t("auth.reset_password")} subtitle={t("auth.reset_password_subtitle")} testId="reset-password-page">
      <form onSubmit={submit} className="space-y-6" data-testid="reset-form">
        {err && <Alert variant="destructive" className="rounded-sm"><AlertDescription>{err}</AlertDescription></Alert>}
        <div className="space-y-2">
          <Label className="overline">Token</Label>
          <Input value={token} onChange={(e) => setToken(e.target.value)} required
            className="rounded-sm h-11 font-mono-plex" data-testid="reset-token-input" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.new_password")}</Label>
          <Input type="password" value={p1} onChange={(e) => setP1(e.target.value)} required
            className="rounded-sm h-11" data-testid="reset-p1-input" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.confirm_password")}</Label>
          <Input type="password" value={p2} onChange={(e) => setP2(e.target.value)} required
            className="rounded-sm h-11" data-testid="reset-p2-input" />
        </div>
        <Button type="submit" disabled={loading} className="w-full h-11 rounded-sm" data-testid="reset-submit-button">
          {loading ? t("common.loading") : t("common.confirm")}
        </Button>
      </form>
      <div className="mt-6">
        <Link to="/login" className="text-xs text-muted-foreground hover:text-foreground">← {t("auth.sign_in")}</Link>
      </div>
    </AuthLayout>
  );
}
