import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Users, ShieldCheck, Files, ClockCounterClockwise, Devices, Bell } from "@phosphor-icons/react";
import { formatDistanceToNow } from "date-fns";
import { it as itLocale } from "date-fns/locale";

function Counter({ label, value, Icon, accent, testId }) {
  return (
    <Card
      className="p-6 rounded-sm border-border card-lift bg-card"
      data-testid={testId}
    >
      <div className="flex items-start justify-between">
        <div className="overline text-muted-foreground">{label}</div>
        <div className={`h-8 w-8 flex items-center justify-center ${accent ? "bg-[hsl(var(--brand-red))] text-white" : "bg-secondary text-foreground"}`}>
          <Icon size={16} weight="duotone" />
        </div>
      </div>
      <div className="mt-6 font-display text-4xl font-black tracking-tight">{value ?? "—"}</div>
    </Card>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: async () => (await api.get("/dashboard/summary")).data,
  });
  const c = data?.counters || {};
  const formatDate = (d) => {
    if (!d) return "—";
    try { return formatDistanceToNow(new Date(d), { addSuffix: true, locale: itLocale }); } catch { return "—"; }
  };

  return (
    <div className="space-y-10" data-testid="dashboard-page">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <div className="overline">{t("dashboard.subtitle")}</div>
          <h1 className="mt-2 font-display text-4xl sm:text-5xl font-black tracking-tight">
            {t("common.welcome")}, {user?.first_name || user?.email?.split("@")[0]}.
          </h1>
        </div>
        <div className="hidden md:block text-right font-mono-plex text-xs text-muted-foreground">
          <div>{new Date().toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long", year: "numeric" })}</div>
          <div className="mt-1">Europe/Rome · EUR</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Counter label={t("dashboard.users_active")} value={c.users_active} Icon={Users} accent testId="counter-users-active" />
        <Counter label={t("dashboard.roles_total")} value={c.roles_total} Icon={ShieldCheck} testId="counter-roles-total" />
        <Counter label={t("dashboard.attachments_total")} value={c.attachments_total} Icon={Files} testId="counter-attachments-total" />
        <Counter label={t("dashboard.audit_last_7d")} value={c.audit_last_7d} Icon={ClockCounterClockwise} testId="counter-audit-7d" />
        <Counter label={t("dashboard.users_total")} value={c.users_total} Icon={Users} testId="counter-users-total" />
        <Counter label={t("dashboard.sessions_active")} value={c.sessions_active} Icon={Devices} testId="counter-sessions-active" />
        <Counter label={t("dashboard.notifications_unread")} value={c.notifications_unread} Icon={Bell} testId="counter-notifications-unread" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="rounded-sm border-border lg:col-span-3 p-6" data-testid="recent-activity-card">
          <div className="flex items-center justify-between mb-6">
            <div>
              <div className="overline">Audit</div>
              <h3 className="font-display text-xl font-bold tracking-tight mt-1">{t("dashboard.recent_activity")}</h3>
            </div>
          </div>
          <div className="divide-y divide-border">
            {(data?.recent_audit || []).map((a) => (
              <div key={a.id} className="py-3 flex items-start gap-4">
                <div className="h-2 w-2 mt-2 bg-[hsl(var(--brand-red))]" aria-hidden />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-mono-plex">{a.action}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {a.user_email || "system"} · {a.entity_type || "—"}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatDate(a.created_at)}
                </div>
              </div>
            ))}
            {(data?.recent_audit || []).length === 0 && (
              <div className="py-8 text-sm text-muted-foreground text-center">{t("common.no_results")}</div>
            )}
          </div>
        </Card>

        <Card className="rounded-sm border-border lg:col-span-2 p-6" data-testid="recent-users-card">
          <div className="overline">Team</div>
          <h3 className="font-display text-xl font-bold tracking-tight mt-1 mb-6">{t("dashboard.recent_users")}</h3>
          <div className="divide-y divide-border">
            {(data?.recent_users || []).map((u) => (
              <div key={u.id} className="py-3 flex items-center gap-3">
                <div className="h-9 w-9 bg-secondary flex items-center justify-center font-mono-plex text-xs font-bold">
                  {((u.first_name?.[0] || "") + (u.last_name?.[0] || "")).toUpperCase() || u.email[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {u.first_name || u.last_name ? `${u.first_name || ""} ${u.last_name || ""}`.trim() : u.email}
                  </div>
                  <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                </div>
                <span className={`text-[10px] font-mono-plex px-2 py-1 ${u.is_active ? "bg-secondary text-foreground" : "bg-destructive/10 text-destructive"}`}>
                  {u.is_active ? "ATTIVO" : "DISATTIVO"}
                </span>
              </div>
            ))}
            {(data?.recent_users || []).length === 0 && (
              <div className="py-8 text-sm text-muted-foreground text-center">{t("common.no_results")}</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
