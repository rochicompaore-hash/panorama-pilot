import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function WhatsAppLogsPage() {
  const { t } = useTranslation();
  const { data } = useQuery({ queryKey: ["whatsapp-logs"], queryFn: async () => (await api.get("/activities/whatsapp-logs", { params: { limit: 100 } })).data });
  const badge = (s) => s === "sent" ? "default" : s === "failed" ? "destructive" : "outline";
  return (
    <div className="space-y-8" data-testid="whatsapp-logs-page">
      <div>
        <div className="overline">Log WhatsApp inviati (mock in dev)</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">Log WhatsApp</h1>
      </div>
      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader><TableRow>
            <TableHead className="overline">Destinatario</TableHead>
            <TableHead className="overline">Corpo</TableHead>
            <TableHead className="overline">Provider</TableHead>
            <TableHead className="overline">Stato</TableHead>
            <TableHead className="overline">Data</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {(data?.items || []).map((l) => (
              <TableRow key={l.id} data-testid={`wa-log-${l.id}`}>
                <TableCell className="font-mono-plex text-xs">{l.to}</TableCell>
                <TableCell className="text-xs truncate max-w-xs">{l.body || l.template_id}</TableCell>
                <TableCell className="text-xs font-mono-plex">{l.provider}</TableCell>
                <TableCell><Badge variant={badge(l.status)} className="rounded-sm text-[10px]">{l.status}</Badge></TableCell>
                <TableCell className="text-xs text-muted-foreground">{l.created_at ? new Date(l.created_at).toLocaleString("it-IT") : ""}</TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-10 text-sm text-muted-foreground">{t("common.no_results")}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
