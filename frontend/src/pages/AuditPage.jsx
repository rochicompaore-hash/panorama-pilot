import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

export default function AuditPage() {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["audit", q],
    queryFn: async () => (await api.get("/audit", { params: { q: q || undefined, limit: 100 } })).data,
  });

  return (
    <div className="space-y-8" data-testid="audit-page">
      <div>
        <div className="overline">{t("audit.subtitle")}</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("audit.title")}</h1>
      </div>

      <Card className="rounded-sm border-border p-4">
        <Input placeholder={t("audit.filter_action")} value={q} onChange={(e) => setQ(e.target.value)}
          className="rounded-sm h-10 max-w-sm font-mono-plex" data-testid="audit-search" />
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("audit.action")}</TableHead>
              <TableHead className="overline">{t("audit.user")}</TableHead>
              <TableHead className="overline">{t("audit.entity")}</TableHead>
              <TableHead className="overline">{t("audit.ip")}</TableHead>
              <TableHead className="overline">{t("audit.when")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.items || []).map((a) => (
              <TableRow key={a.id} data-testid={`audit-row-${a.id}`}>
                <TableCell><Badge variant="outline" className="rounded-sm font-mono-plex text-[10px]">{a.action}</Badge></TableCell>
                <TableCell className="text-xs">{a.user_email || "system"}</TableCell>
                <TableCell className="text-xs">
                  {a.entity_type ? <span className="font-mono-plex">{a.entity_type}{a.entity_id ? `:${a.entity_id.slice(0,8)}` : ""}</span> : "—"}
                </TableCell>
                <TableCell className="text-xs font-mono-plex">{a.ip || "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {a.created_at ? new Date(a.created_at).toLocaleString("it-IT") : "—"}
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
