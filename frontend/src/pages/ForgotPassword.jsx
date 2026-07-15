import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AuthLayout from "@/layouts/AuthLayout";
import { api, formatApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function ForgotPassword() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: email.trim() });
      setOk(true);
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title={t("auth.reset_password")} subtitle={t("auth.reset_password_subtitle")} testId="forgot-password-page">
      {ok ? (
        <Alert className="rounded-sm" data-testid="forgot-success">
          <AlertDescription>{t("auth.reset_password_success")}</AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={submit} className="space-y-6" data-testid="forgot-form">
          {err && <Alert variant="destructive" className="rounded-sm"><AlertDescription>{err}</AlertDescription></Alert>}
          <div className="space-y-2">
            <Label htmlFor="email" className="overline">{t("common.email")}</Label>
            <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="rounded-sm h-11" data-testid="forgot-email-input" />
          </div>
          <Button type="submit" disabled={loading} className="w-full h-11 rounded-sm" data-testid="forgot-submit-button">
            {loading ? t("common.loading") : t("common.confirm")}
          </Button>
        </form>
      )}
      <div className="mt-6">
        <Link to="/login" className="text-xs text-muted-foreground hover:text-foreground" data-testid="forgot-back-login">
          ← {t("auth.sign_in")}
        </Link>
      </div>
    </AuthLayout>
  );
}
