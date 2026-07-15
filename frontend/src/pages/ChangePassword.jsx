import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/contexts/AuthContext";
import AuthLayout from "@/layouts/AuthLayout";
import { api, formatApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";

export default function ChangePassword() {
  const { t } = useTranslation();
  const { user, loadMe } = useAuth();
  const navigate = useNavigate();
  const [cur, setCur] = useState(""); const [p1, setP1] = useState(""); const [p2, setP2] = useState("");
  const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setErr("");
    if (p1.length < 8) return setErr(t("auth.password_min"));
    if (p1 !== p2) return setErr(t("auth.passwords_dont_match"));
    setLoading(true);
    try {
      await api.post("/auth/change-password", { current_password: cur, new_password: p1 });
      toast.success(t("toast.saved"));
      // sessions revoked → login needed
      localStorage.removeItem("ie_access_token");
      localStorage.removeItem("ie_refresh_token");
      await loadMe();
      navigate("/login");
    } catch (e2) {
      setErr(formatApiError(e2.response?.data?.detail) || e2.message);
    } finally { setLoading(false); }
  };

  return (
    <AuthLayout
      title={t("auth.change_password")}
      subtitle={user?.must_change_password ? t("auth.must_change_password") : undefined}
      testId="change-password-page"
    >
      <form onSubmit={submit} className="space-y-5" data-testid="change-password-form">
        {err && <Alert variant="destructive" className="rounded-sm"><AlertDescription>{err}</AlertDescription></Alert>}
        <div className="space-y-2">
          <Label className="overline">{t("auth.current_password")}</Label>
          <Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} required
            className="rounded-sm h-11" data-testid="cp-current-input" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.new_password")}</Label>
          <Input type="password" value={p1} onChange={(e) => setP1(e.target.value)} required
            className="rounded-sm h-11" data-testid="cp-p1-input" />
        </div>
        <div className="space-y-2">
          <Label className="overline">{t("auth.confirm_password")}</Label>
          <Input type="password" value={p2} onChange={(e) => setP2(e.target.value)} required
            className="rounded-sm h-11" data-testid="cp-p2-input" />
        </div>
        <Button type="submit" disabled={loading} className="w-full h-11 rounded-sm" data-testid="cp-submit-button">
          {loading ? t("common.loading") : t("auth.change_password")}
        </Button>
      </form>
    </AuthLayout>
  );
}
