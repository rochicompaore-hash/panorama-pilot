import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Users, ShieldCheck, Files, ClockCounterClockwise, Devices, Bell,
  Target, TrendUp, Warning, CalendarBlank, ListChecks, Trophy, ChartBar,
} from "@phosphor-icons/react";

function fmtEUR(n) { try { return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0); } catch { return "€ 0"; } }

function Counter({ label, value, Icon, accent, testId, hint }) {
  return (
    <Card className="p-6 rounded-sm border-border card-lift bg-card" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div className="overline text-muted-foreground">{label}</div>
        <div className={`h-8 w-8 flex items-center justify-center ${accent ? "bg-[hsl(var(--brand-red))] text-white" : "bg-secondary text-foreground"}`}>
          <Icon size={16} weight="duotone" />
        </div>
      </div>
      <div className="mt-6 font-display text-3xl font-black tracking-tight">{value ?? "—"}</div>
      {hint && <div className="mt-1 text-[10px] font-mono-plex text-muted-foreground uppercase">{hint}</div>}
    </Card>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: variant } = useQuery({ queryKey: ["dashboard-variant"], queryFn: async () => (await api.get("/dashboard-crm/variant")).data });
  const v = variant?.variant;

  return (
    <div className="space-y-10" data-testid="dashboard-page">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="overline">{v === "direction" ? "Vista direzione" : v === "sales" ? "Vista commerciale" : v === "installer" ? "Vista posatore" : "Panoramica"}</div>
          <h1 className="mt-2 font-display text-4xl sm:text-5xl font-black tracking-tight">
            {t("common.welcome")}, {user?.first_name || user?.email?.split("@")[0]}.
          </h1>
        </div>
        <div className="hidden md:block text-right font-mono-plex text-xs text-muted-foreground">
          <div>{new Date().toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long", year: "numeric" })}</div>
          <div className="mt-1">Europe/Rome · EUR</div>
        </div>
      </div>

      {v === "direction" && <DirectionDashboard />}
      {v === "sales" && <SalesDashboard navigate={navigate} />}
      {v === "installer" && <InstallerDashboard />}
      {!v && <CoreDashboard />}
    </div>
  );
}

function SalesDashboard({ navigate }) {
  const { t } = useTranslation();
  const { data } = useQuery({ queryKey: ["dash-sales"], queryFn: async () => (await api.get("/dashboard-crm/sales")).data });
  const c = data?.counters || {};
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Counter label={t("dashboard_sales.leads_open")} value={c.leads_open} Icon={Users} accent testId="cs-leads-open" />
        <Counter label={t("dashboard_sales.leads_won_month")} value={c.leads_won_month} Icon={Trophy} testId="cs-won" />
        <Counter label={t("dashboard_sales.appointments_today")} value={c.appointments_today} Icon={CalendarBlank} testId="cs-appt" />
        <Counter label={t("dashboard_sales.tasks_open")} value={c.tasks_open} Icon={ListChecks} testId="cs-tasks" hint={c.tasks_overdue ? `${c.tasks_overdue} in ritardo` : null} />
        <Counter label={t("dashboard_sales.weighted_pipeline_value")} value={fmtEUR(c.weighted_pipeline_value)} Icon={TrendUp} testId="cs-weighted" />
        <Counter label={t("dashboard_sales.potential_pipeline_value")} value={fmtEUR(c.potential_pipeline_value)} Icon={ChartBar} testId="cs-potential" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="rounded-sm border-border p-6" data-testid="cs-next-actions">
          <div className="overline">Vendita</div>
          <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-4">{t("dashboard_sales.next_actions")}</h3>
          <div className="divide-y divide-border">
            {(data?.next_actions || []).map((l) => (
              <button key={l.id} onClick={() => navigate(`/leads/${l.id}`)} className="w-full py-3 flex items-center gap-3 text-left hover:bg-secondary px-2" data-testid={`cs-todo-${l.id}`}>
                <Warning size={14} weight="bold" className="text-[hsl(var(--brand-red))]" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{`${l.first_name || ""} ${l.last_name || ""}`.trim() || l.company_name || l.email}</div>
                  <div className="text-xs text-muted-foreground truncate">{l.intelligence?.next_action_suggestion?.label}</div>
                </div>
                <div className="text-xs text-muted-foreground font-mono-plex whitespace-nowrap">{fmtEUR(l.estimated_value)}</div>
              </button>
            ))}
            {(data?.next_actions || []).length === 0 && <div className="py-8 text-sm text-muted-foreground text-center">Nessuna azione pendente</div>}
          </div>
        </Card>
        <Card className="rounded-sm border-border p-6" data-testid="cs-goals">
          <div className="overline">Obiettivi</div>
          <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-4">I miei obiettivi</h3>
          <div className="space-y-4">
            {(data?.goals || []).map((g) => {
              const pct = g.target_value > 0 ? Math.min(100, Math.round((g.achieved_value / g.target_value) * 100)) : 0;
              return (
                <div key={g.id} data-testid={`cs-goal-${g.id}`}>
                  <div className="flex items-baseline justify-between">
                    <div>
                      <div className="text-sm font-medium capitalize">{g.metric}</div>
                      <div className="text-[10px] font-mono-plex text-muted-foreground uppercase">{g.period_type}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono-plex text-sm">{g.metric === "revenue" ? fmtEUR(g.achieved_value) : g.achieved_value}<span className="text-muted-foreground"> / {g.metric === "revenue" ? fmtEUR(g.target_value) : g.target_value}</span></div>
                      <div className="text-[10px] text-[hsl(var(--brand-red))] font-mono-plex">{pct}%</div>
                    </div>
                  </div>
                  <Progress value={pct} className="mt-2 h-1" />
                </div>
              );
            })}
            {(data?.goals || []).length === 0 && <div className="py-4 text-sm text-muted-foreground text-center">Nessun obiettivo attivo</div>}
          </div>
        </Card>
      </div>
    </>
  );
}

function DirectionDashboard() {
  const { t } = useTranslation();
  const { data } = useQuery({ queryKey: ["dash-direction"], queryFn: async () => (await api.get("/dashboard-crm/direction")).data });
  const c = data?.counters || {};
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Counter label={t("dashboard_direction.won_month")} value={c.won_month} Icon={Trophy} accent testId="cd-won" />
        <Counter label={t("dashboard_direction.won_value_month")} value={fmtEUR(c.won_value_month)} Icon={TrendUp} testId="cd-value" />
        <Counter label={t("dashboard_direction.conversion_rate")} value={`${c.conversion_rate_month || 0}%`} Icon={ChartBar} testId="cd-conv" />
        <Counter label="Clienti totali" value={c.customers_total} Icon={Users} testId="cd-customers" />
        <Counter label={t("dashboard_direction.open_pipeline")} value={fmtEUR(c.open_pipeline_value)} Icon={ChartBar} testId="cd-pipeline" />
        <Counter label={t("dashboard_direction.weighted")} value={fmtEUR(c.weighted_pipeline_value)} Icon={TrendUp} testId="cd-weighted" />
        <Counter label="Lead aperti" value={c.open_leads} Icon={Users} testId="cd-leads-open" />
        <Counter label="Attività (7g)" value={c.activities_7d} Icon={ClockCounterClockwise} testId="cd-activities" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="rounded-sm border-border p-6" data-testid="cd-top">
          <div className="overline">Team</div>
          <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-4">{t("dashboard_direction.top_performers")}</h3>
          <div className="divide-y divide-border">
            {(data?.top_performers || []).map((p) => (
              <div key={p.user_id} className="py-3 flex items-center justify-between" data-testid={`cd-tp-${p.user_id}`}>
                <div className="text-sm font-medium truncate">{p.name}</div>
                <div className="text-right">
                  <div className="font-mono-plex text-sm">{fmtEUR(p.won_value)}</div>
                  <div className="text-[10px] text-muted-foreground font-mono-plex">{p.won_count} vinti</div>
                </div>
              </div>
            ))}
            {(data?.top_performers || []).length === 0 && <div className="py-8 text-sm text-muted-foreground text-center">Nessun dato</div>}
          </div>
        </Card>
        <Card className="rounded-sm border-border p-6" data-testid="cd-stages">
          <div className="overline">Pipeline</div>
          <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-4">{t("dashboard_direction.stage_breakdown")}</h3>
          <div className="space-y-2">
            {(data?.stage_breakdown || []).map((s) => (
              <div key={s.stage} className="flex items-center gap-3" data-testid={`cd-stage-${s.stage}`}>
                <span className="h-2 w-2" style={{ background: s.color }} />
                <div className="text-sm flex-1">{s.stage}</div>
                <div className="font-mono-plex text-sm font-bold">{s.count}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}

function InstallerDashboard() {
  const { data } = useQuery({ queryKey: ["dash-installer"], queryFn: async () => (await api.get("/dashboard-crm/installer")).data });
  return (
    <div>
      <Counter label="Appuntamenti oggi" value={data?.counters?.appointments_today || 0} Icon={CalendarBlank} accent testId="ci-appt" />
      <Card className="rounded-sm border-border p-6 mt-4">
        <div className="overline">Oggi</div>
        <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-4">Interventi programmati</h3>
        <div className="divide-y divide-border">
          {(data?.appointments_today || []).map(a => (
            <div key={a.id} className="py-3">
              <div className="text-sm font-medium">{a.title}</div>
              <div className="text-xs text-muted-foreground">{a.location} · {new Date(a.start_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</div>
            </div>
          ))}
          {(data?.appointments_today || []).length === 0 && <div className="py-6 text-sm text-muted-foreground text-center">Nessun intervento oggi</div>}
        </div>
        <div className="mt-4 text-xs text-muted-foreground">{data?.message}</div>
      </Card>
    </div>
  );
}

function CoreDashboard() {
  const { data } = useQuery({ queryKey: ["dashboard-summary"], queryFn: async () => (await api.get("/dashboard/summary")).data });
  const c = data?.counters || {};
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Counter label="Utenti attivi" value={c.users_active} Icon={Users} accent testId="core-users" />
      <Counter label="Ruoli" value={c.roles_total} Icon={ShieldCheck} testId="core-roles" />
      <Counter label="Allegati" value={c.attachments_total} Icon={Files} testId="core-attachments" />
      <Counter label="Audit (7g)" value={c.audit_last_7d} Icon={ClockCounterClockwise} testId="core-audit" />
    </div>
  );
}
