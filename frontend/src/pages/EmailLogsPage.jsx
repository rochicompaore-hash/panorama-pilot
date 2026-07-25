import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { ArrowClockwise, MagnifyingGlass, Eye } from "@phosphor-icons/react";

const STATUS_VARIANT = {
  sent: "default",
  test_intercepted: "default",
  failed: "destructive",
  retrying: "outline",
  configuration_required: "secondary",
  queued: "outline",
  sending: "outline",
  bounced: "destructive",
};

const STATUSES = [
  "sent", "test_intercepted", "queued", "sending", "retrying",
  "failed", "bounced", "configuration_required",
];

export default function EmailLogsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [toFilter, setToFilter] = useState("");
  const [detailId, setDetailId] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["email-logs", statusFilter, toFilter],
    queryFn: async () => {
      const params = { limit: 100 };
      if (statusFilter) params.status = statusFilter;
      if (toFilter) params.to = toFilter;
      return (await api.get("/email-logs", { params })).data;
    },
  });

  const detail = useQuery({
    queryKey: ["email-log", detailId],
    queryFn: async () => (await api.get(`/email-logs/${detailId}`)).data,
    enabled: !!detailId,
  });

  const retry = useMutation({
    mutationFn: async (id) => (await api.post(`/email-logs/${id}/retry`)).data,
    onSuccess: (data) => {
      toast.success(`Retry — nuovo stato: ${data.status}`);
      qc.invalidateQueries({ queryKey: ["email-logs"] });
    },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });

  return (
    <div className="space-y-8" data-testid="email-logs-page">
      <div>
        <div className="overline text-muted-foreground">Registro invii email</div>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">
          Registro email
        </h1>
        <p className="text-sm text-muted-foreground mt-2">
          Log tenant-isolato di tutte le email tentate dal sistema (invito, reset, preventivi,
          contratti, alert AI CFO, riepiloghi giornalieri, ecc.).
        </p>
      </div>

      {/* Status counts */}
      {data?.counts_by_status && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2" data-testid="email-log-counts">
          {STATUSES.map((s) => {
            const n = data.counts_by_status[s] || 0;
            if (n === 0 && s !== "sent") return null;
            return (
              <button
                key={s}
                onClick={() => setStatusFilter(statusFilter === s ? "" : s)}
                className={`text-left border rounded-sm p-3 hover:border-primary transition ${
                  statusFilter === s ? "border-primary bg-muted/40" : "border-border"
                }`}
                data-testid={`filter-status-${s}`}
              >
                <div className="text-2xl font-black">{n}</div>
                <div className="text-xs text-muted-foreground">{s}</div>
              </button>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <Card className="p-4 rounded-sm border-border flex flex-wrap items-end gap-3" data-testid="email-log-filters">
        <div className="flex-1 min-w-[200px]">
          <div className="text-xs uppercase text-muted-foreground font-mono-plex mb-1">Destinatario</div>
          <div className="relative">
            <MagnifyingGlass size={14} className="absolute left-2 top-2.5 text-muted-foreground" />
            <Input
              className="pl-7"
              placeholder="Cerca per email…"
              value={toFilter}
              onChange={(e) => setToFilter(e.target.value)}
              data-testid="filter-to-input"
            />
          </div>
        </div>
        <div className="min-w-[180px]">
          <div className="text-xs uppercase text-muted-foreground font-mono-plex mb-1">Stato</div>
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger data-testid="filter-status-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti</SelectItem>
              {STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button size="sm" variant="outline" onClick={() => qc.invalidateQueries({ queryKey: ["email-logs"] })}>
          <ArrowClockwise size={14} className="mr-2" /> Aggiorna
        </Button>
      </Card>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">Data</TableHead>
              <TableHead className="overline">Destinatario</TableHead>
              <TableHead className="overline">Oggetto</TableHead>
              <TableHead className="overline">Template</TableHead>
              <TableHead className="overline">Modalità</TableHead>
              <TableHead className="overline">Tentativi</TableHead>
              <TableHead className="overline">Stato</TableHead>
              <TableHead className="overline text-right">Azioni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground text-sm">Caricamento…</TableCell></TableRow>}
            {(data?.items || []).map((l) => (
              <TableRow key={l.id} data-testid={`email-log-${l.id}`}>
                <TableCell className="text-xs text-muted-foreground">
                  {l.created_at ? new Date(l.created_at).toLocaleString("it-IT") : "—"}
                </TableCell>
                <TableCell className="text-xs">
                  <div className="font-mono-plex">{l.to}</div>
                  {l.original_to && l.original_to !== l.to && (
                    <div className="text-[10px] text-amber-700 mt-0.5">→ orig: {l.original_to}</div>
                  )}
                </TableCell>
                <TableCell className="text-xs max-w-[280px] truncate">{l.subject}</TableCell>
                <TableCell className="text-xs font-mono-plex">{l.template}</TableCell>
                <TableCell>
                  {l.delivery_mode && (
                    <Badge variant={l.delivery_mode === "live" ? "default" : "secondary"} className="rounded-sm text-[10px]">
                      {l.delivery_mode}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-xs font-mono-plex">
                  {l.attempt_count || 0}/{l.max_attempts || 3}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[l.status] || "outline"} className="rounded-sm text-[10px]">
                    {l.status}
                  </Badge>
                  {l.error && <div className="text-[10px] text-red-600 mt-1 max-w-[180px] truncate">{l.error}</div>}
                </TableCell>
                <TableCell className="text-right">
                  <Button size="icon" variant="ghost" onClick={() => setDetailId(l.id)} data-testid={`view-${l.id}`}>
                    <Eye size={14} />
                  </Button>
                  {(l.status === "failed" || l.status === "retrying" || l.status === "configuration_required") && (
                    <Button
                      size="icon" variant="ghost"
                      disabled={retry.isPending}
                      onClick={() => retry.mutate(l.id)}
                      data-testid={`retry-${l.id}`}
                    >
                      <ArrowClockwise size={14} />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {(data?.items || []).length === 0 && !isLoading && (
              <TableRow><TableCell colSpan={8} className="text-center py-10 text-sm text-muted-foreground">Nessuna email registrata.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {/* Detail dialog */}
      <Dialog open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="email-log-detail">
          <DialogHeader>
            <DialogTitle>Dettaglio email</DialogTitle>
            <DialogDescription>
              Log ID: <code className="text-xs">{detailId}</code>
            </DialogDescription>
          </DialogHeader>
          {detail.data && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div><b>Stato:</b> <Badge className="rounded-sm ml-1">{detail.data.status}</Badge></div>
                <div><b>Provider:</b> {detail.data.provider}</div>
                <div><b>Modalità:</b> {detail.data.delivery_mode}</div>
                <div><b>Tentativi:</b> {detail.data.attempt_count}/{detail.data.max_attempts}</div>
                <div><b>Destinatario:</b> {detail.data.to}</div>
                <div><b>Orig:</b> {detail.data.original_to}</div>
                <div><b>Template:</b> {detail.data.template} v{detail.data.template_version ?? "?"}</div>
                <div><b>Reply-To:</b> {detail.data.reply_to || "—"}</div>
                <div className="col-span-2"><b>Oggetto:</b> {detail.data.subject}</div>
                {detail.data.error && <div className="col-span-2 text-red-600"><b>Errore:</b> {detail.data.error}</div>}
                {detail.data.smtp_response && <div className="col-span-2 text-xs"><b>SMTP resp:</b> <code>{detail.data.smtp_response}</code></div>}
                <div className="col-span-2 text-xs"><b>Payload hash:</b> <code>{detail.data.payload_hash}</code></div>
                {detail.data.idempotency_key && <div className="col-span-2 text-xs"><b>Idempotency key:</b> <code>{detail.data.idempotency_key}</code></div>}
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-2">Anteprima HTML inviata</div>
                <div className="border rounded-sm p-3 bg-muted/30 max-h-[300px] overflow-auto">
                  <div dangerouslySetInnerHTML={{ __html: detail.data.stored_html || "" }} />
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-2">Testo</div>
                <pre className="border rounded-sm p-3 bg-muted/30 text-xs whitespace-pre-wrap font-mono-plex max-h-[200px] overflow-auto">
                  {detail.data.stored_text || "—"}
                </pre>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
