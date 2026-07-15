import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF"];
const TIMEZONES = ["Europe/Rome", "Europe/London", "Europe/Berlin", "Europe/Paris", "UTC"];

export default function CompanyPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const readOnly = !has("company.edit");
  const { data } = useQuery({ queryKey: ["company"], queryFn: async () => (await api.get("/company")).data });
  const [form, setForm] = useState({});

  useEffect(() => { if (data) setForm({ ...data, settings: { ...(data.settings || {}) } }); }, [data]);

  const mut = useMutation({
    mutationFn: async (payload) => (await api.patch("/company", payload)).data,
    onSuccess: () => { toast.success(t("company.saved")); qc.invalidateQueries({ queryKey: ["company"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const upd = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const updS = (k, v) => setForm(f => ({ ...f, settings: { ...(f.settings || {}), [k]: v } }));

  const submit = (e) => {
    e.preventDefault();
    const { name, legal_name, vat_number, tax_code, address, city, zip_code, province, country, phone, email, website, logo_url, settings } = form;
    mut.mutate({ name, legal_name, vat_number, tax_code, address, city, zip_code, province, country, phone, email, website, logo_url, settings });
  };

  return (
    <div className="space-y-8" data-testid="company-page">
      <div>
        <div className="overline">{t("company.subtitle")}</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("company.title")}</h1>
      </div>

      <form onSubmit={submit} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="rounded-sm border-border p-6 lg:col-span-2 space-y-4" data-testid="company-general-card">
          <div className="overline">Anagrafica</div>
          <Field label={t("company.name")} value={form.name || ""} onChange={(v) => upd("name", v)} readOnly={readOnly} testId="c-name" />
          <Field label={t("company.legal_name")} value={form.legal_name || ""} onChange={(v) => upd("legal_name", v)} readOnly={readOnly} testId="c-legal" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={t("company.vat_number")} value={form.vat_number || ""} onChange={(v) => upd("vat_number", v)} readOnly={readOnly} testId="c-vat" />
            <Field label={t("company.tax_code")} value={form.tax_code || ""} onChange={(v) => upd("tax_code", v)} readOnly={readOnly} testId="c-taxcode" />
          </div>
          <Field label={t("company.address")} value={form.address || ""} onChange={(v) => upd("address", v)} readOnly={readOnly} testId="c-address" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Field label={t("company.city")} value={form.city || ""} onChange={(v) => upd("city", v)} readOnly={readOnly} testId="c-city" />
            <Field label={t("company.zip")} value={form.zip_code || ""} onChange={(v) => upd("zip_code", v)} readOnly={readOnly} testId="c-zip" />
            <Field label={t("company.province")} value={form.province || ""} onChange={(v) => upd("province", v)} readOnly={readOnly} testId="c-prov" />
            <Field label={t("company.country")} value={form.country || ""} onChange={(v) => upd("country", v)} readOnly={readOnly} testId="c-country" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={t("company.phone")} value={form.phone || ""} onChange={(v) => upd("phone", v)} readOnly={readOnly} testId="c-phone" />
            <Field label={t("company.email")} value={form.email || ""} onChange={(v) => upd("email", v)} readOnly={readOnly} testId="c-email" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label={t("company.website")} value={form.website || ""} onChange={(v) => upd("website", v)} readOnly={readOnly} testId="c-website" />
            <Field label={t("company.logo_url")} value={form.logo_url || ""} onChange={(v) => upd("logo_url", v)} readOnly={readOnly} testId="c-logo" />
          </div>
        </Card>

        <Card className="rounded-sm border-border p-6 space-y-4 h-fit" data-testid="company-settings-card">
          <div className="overline">Localizzazione</div>
          <div className="space-y-1.5">
            <Label className="overline">{t("company.locale")}</Label>
            <div className="text-sm font-mono-plex px-3 py-2 bg-secondary border border-border">
              {form.settings?.locale || "it"} (fisso in M1)
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="overline">{t("company.currency")}</Label>
            <Select value={form.settings?.currency || "EUR"} onValueChange={(v) => updS("currency", v)} disabled={readOnly}>
              <SelectTrigger className="rounded-sm h-10" data-testid="c-currency"><SelectValue /></SelectTrigger>
              <SelectContent>{CURRENCIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="overline">{t("company.timezone")}</Label>
            <Select value={form.settings?.timezone || "Europe/Rome"} onValueChange={(v) => updS("timezone", v)} disabled={readOnly}>
              <SelectTrigger className="rounded-sm h-10" data-testid="c-timezone"><SelectValue /></SelectTrigger>
              <SelectContent>{TIMEZONES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {!readOnly && (
            <Button type="submit" disabled={mut.isPending} className="w-full rounded-sm h-11" data-testid="company-save">
              {mut.isPending ? t("common.loading") : t("common.save")}
            </Button>
          )}
        </Card>
      </form>
    </div>
  );
}

function Field({ label, value, onChange, readOnly, testId }) {
  return (
    <div className="space-y-1.5">
      <Label className="overline">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} disabled={readOnly} className="rounded-sm h-10" data-testid={testId} />
    </div>
  );
}
