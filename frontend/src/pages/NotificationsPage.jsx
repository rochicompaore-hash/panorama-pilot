import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bell } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function NotificationsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["notifications-list"], queryFn: async () => (await api.get("/notifications", { params: { limit: 100 } })).data });
  const markAll = useMutation({ mutationFn: async () => (await api.post("/notifications/read-all")).data, onSuccess: () => { toast.success(t("toast.saved")); qc.invalidateQueries({ queryKey: ["notifications-list"] }); } });
  const markOne = useMutation({ mutationFn: async (id) => (await api.post(`/notifications/${id}/read`)).data, onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications-list"] }) });

  return (
    <div className="space-y-8" data-testid="notifications-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("notifications.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("notifications.title")}</h1>
        </div>
        {(data?.unread || 0) > 0 && (
          <Button variant="outline" className="rounded-sm" onClick={() => markAll.mutate()} data-testid="mark-all-read-button">
            {t("notifications.mark_all_read")} ({data.unread})
          </Button>
        )}
      </div>

      <Card className="rounded-sm border-border divide-y divide-border">
        {(data?.items || []).length === 0 && (
          <div className="p-12 text-center">
            <Bell size={40} className="mx-auto text-muted-foreground mb-3" weight="duotone" />
            <div className="text-sm text-muted-foreground">{t("notifications.empty")}</div>
          </div>
        )}
        {(data?.items || []).map((n) => (
          <button
            key={n.id}
            onClick={() => !n.read_at && markOne.mutate(n.id)}
            className={`w-full text-left p-5 hover:bg-secondary transition-colors ${!n.read_at ? "bg-secondary/50" : ""}`}
            data-testid={`notification-${n.id}`}
          >
            <div className="flex items-start gap-3">
              {!n.read_at && <div className="h-2 w-2 mt-2 bg-[hsl(var(--brand-red))]" />}
              <div className="flex-1">
                <div className="text-sm font-medium">{n.title}</div>
                {n.body && <div className="text-xs text-muted-foreground mt-1">{n.body}</div>}
              </div>
              <div className="text-xs text-muted-foreground whitespace-nowrap">{n.created_at ? new Date(n.created_at).toLocaleString("it-IT") : ""}</div>
            </div>
          </button>
        ))}
      </Card>
    </div>
  );
}
