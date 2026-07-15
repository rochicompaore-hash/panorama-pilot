import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

export default function SessionsPage() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["my-sessions"], queryFn: async () => (await api.get("/sessions/mine")).data });

  const revokeMut = useMutation({
    mutationFn: async (id) => (await api.post(`/sessions/${id}/revoke`)).data,
    onSuccess: () => { toast.success(t("sessions.revoked")); qc.invalidateQueries({ queryKey: ["my-sessions"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  const doLogoutAll = async () => {
    await logout(true);
    toast.success("Sessioni terminate");
    navigate("/login");
  };

  return (
    <div className="space-y-8" data-testid="sessions-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("sessions.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("sessions.title")}</h1>
        </div>
        <Button variant="destructive" className="rounded-sm" onClick={doLogoutAll} data-testid="logout-all-button">
          {t("sessions.logout_all")}
        </Button>
      </div>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("sessions.device")}</TableHead>
              <TableHead className="overline">{t("sessions.ip")}</TableHead>
              <TableHead className="overline">{t("sessions.last_used")}</TableHead>
              <TableHead className="overline">{t("common.status")}</TableHead>
              <TableHead className="overline text-right">{t("common.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((s) => (
              <TableRow key={s.id} data-testid={`session-row-${s.id}`}>
                <TableCell className="text-xs max-w-md truncate">{s.device_info || s.user_agent || "—"}</TableCell>
                <TableCell className="font-mono-plex text-xs">{s.ip || "—"}</TableCell>
                <TableCell className="text-xs">{s.last_used_at ? new Date(s.last_used_at).toLocaleString("it-IT") : "—"}</TableCell>
                <TableCell>
                  {s.revoked_at
                    ? <span className="text-[10px] font-mono-plex bg-destructive/10 text-destructive px-2 py-1">REVOCATA</span>
                    : <span className="text-[10px] font-mono-plex bg-secondary px-2 py-1">ATTIVA</span>}
                </TableCell>
                <TableCell className="text-right">
                  {!s.revoked_at && (
                    <Button variant="outline" size="sm" className="rounded-sm" onClick={() => revokeMut.mutate(s.id)} data-testid={`revoke-session-${s.id}`}>
                      {t("sessions.revoke")}
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
