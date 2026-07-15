import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

export default function EmailLogsPage() {
  const { t } = useTranslation();
  const { data } = useQuery({ queryKey: ["email-logs"], queryFn: async () => (await api.get("/email-logs", { params: { limit: 100 } })).data });

  const badgeVariant = (s) => s === "sent" ? "default" : s === "failed" ? "destructive" : "outline";

  return (
    <div className="space-y-8" data-testid="email-logs-page">
      <div>
        <div className="overline">{t("email_logs.subtitle")}</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("email_logs.title")}</h1>
      </div>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("email_logs.to")}</TableHead>
              <TableHead className="overline">{t("email_logs.subject")}</TableHead>
              <TableHead className="overline">{t("email_logs.template")}</TableHead>
              <TableHead className="overline">{t("email_logs.provider")}</TableHead>
              <TableHead className="overline">{t("email_logs.status")}</TableHead>
              <TableHead className="overline">{t("common.created_at")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((l) => (
              <TableRow key={l.id} data-testid={`email-log-${l.id}`}>
                <TableCell className="font-mono-plex text-xs">{l.to}</TableCell>
                <TableCell className="text-xs">{l.subject}</TableCell>
                <TableCell className="text-xs font-mono-plex">{l.template}</TableCell>
                <TableCell className="text-xs font-mono-plex">{l.provider}</TableCell>
                <TableCell><Badge variant={badgeVariant(l.status)} className="rounded-sm text-[10px]">{l.status}</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">{l.created_at ? new Date(l.created_at).toLocaleString("it-IT") : ""}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && (
              <TableRow><TableCell colSpan={6} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
