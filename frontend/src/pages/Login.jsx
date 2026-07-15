import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/contexts/AuthContext";
import AuthLayout from "@/layouts/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { formatApiError } from "@/api/client";
import { ArrowRight } from "@phosphor-icons/react";

export default function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(email.trim(), password);
      if (res.must_change_password) {
        navigate("/change-password");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title={t("auth.sign_in")} subtitle={t("auth.sign_in_subtitle")} testId="login-page">
      <form onSubmit={submit} className="space-y-6" data-testid="login-form">
        {error && (
          <Alert variant="destructive" className="rounded-sm" data-testid="login-error">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <Label htmlFor="email" className="overline">{t("common.email")}</Label>
          <Input
            id="email" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder={t("auth.email_placeholder")}
            className="rounded-sm h-11" data-testid="login-email-input"
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password" className="overline">{t("common.password")}</Label>
            <Link to="/forgot-password" className="text-xs text-muted-foreground hover:text-foreground" data-testid="login-forgot-link">
              {t("auth.forgot_password")}
            </Link>
          </div>
          <Input
            id="password" type="password" autoComplete="current-password" required
            value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder={t("auth.password_placeholder")}
            className="rounded-sm h-11" data-testid="login-password-input"
          />
        </div>
        <Button
          type="submit"
          disabled={loading}
          className="w-full h-11 rounded-sm bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] transition-transform"
          data-testid="login-submit-button"
        >
          {loading ? t("common.loading") : t("auth.sign_in")}
          <ArrowRight size={16} className="ml-2" />
        </Button>
        <div className="pt-4 border-t border-border">
          <p className="text-xs text-muted-foreground text-center leading-relaxed">
            Ambiente sicuro · autenticazione a doppio token · brute-force protection attiva
          </p>
        </div>
      </form>
    </AuthLayout>
  );
}
