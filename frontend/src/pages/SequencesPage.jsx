import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Play } from "@phosphor-icons/react";

export default function SequencesPage() {
  const { t } = useTranslation();
  const { has } = useAuth();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["sequences"], queryFn: async () => (await api.get("/sequences")).data });
  const items = data?.items || [];
  const [openCreate, setOpenCreate] = useState(false);

  const createMut = useMutation({
    mutationFn: async (payload) => (await api.post("/sequences", payload)).data,
    onSuccess: () => { toast.success(t("toast.created")); qc.invalidateQueries({ queryKey: ["sequences"] }); setOpenCreate(false); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const updateMut = useMutation({
    mutationFn: async ({ id, patch }) => (await api.patch(`/sequences/${id}`, patch)).data,
    onSuccess: () => { toast.success(t("toast.saved")); qc.invalidateQueries({ queryKey: ["sequences"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });
  const nextMut = useMutation({
    mutationFn: async (id) => (await api.post(`/sequences/${id}/next`)).data,
    onSuccess: (data) => { toast.success(`Nuovo numero: ${data.formatted}`); qc.invalidateQueries({ queryKey: ["sequences"] }); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail) || e.message),
  });

  return (
    <div className="space-y-8" data-testid="sequences-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">{t("sequences.subtitle")}</div>
          <h1 className="mt-2 font-display text-3xl sm:text-4xl font-black tracking-tight">{t("sequences.title")}</h1>
        </div>
        {has("sequences.manage") && (
          <Dialog open={openCreate} onOpenChange={setOpenCreate}>
            <DialogTrigger asChild>
              <Button className="rounded-sm h-11 gap-2" data-testid="new-sequence-button"><Plus size={16} weight="bold" />{t("sequences.add")}</Button>
            </DialogTrigger>
            <CreateSequenceDialog onSubmit={(p) => createMut.mutate(p)} loading={createMut.isPending} />
          </Dialog>
        )}
      </div>

      <Card className="rounded-sm border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">{t("sequences.key")}</TableHead>
              <TableHead className="overline">{t("sequences.label")}</TableHead>
              <TableHead className="overline">{t("sequences.prefix")}</TableHead>
              <TableHead className="overline">{t("sequences.padding")}</TableHead>
              <TableHead className="overline">{t("sequences.year_reset")}</TableHead>
              <TableHead className="overline">{t("sequences.current_number")}</TableHead>
              <TableHead className="overline">{t("sequences.next_preview")}</TableHead>
              <TableHead className="overline text-right">{t("common.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((s) => (
              <TableRow key={s.id} data-testid={`sequence-row-${s.key}`}>
                <TableCell className="font-mono-plex text-xs">{s.key}</TableCell>
                <TableCell>{s.label}</TableCell>
                <TableCell className="font-mono-plex">{s.prefix || "—"}</TableCell>
                <TableCell className="font-mono-plex">{s.padding}</TableCell>
                <TableCell>
                  <Switch
                    checked={s.year_reset}
                    onCheckedChange={(v) => has("sequences.manage") && updateMut.mutate({ id: s.id, patch: { year_reset: v } })}
                    disabled={!has("sequences.manage")}
                    data-testid={`seq-yearreset-${s.key}`}
                  />
                </TableCell>
                <TableCell className="font-mono-plex">{s.current_number}</TableCell>
                <TableCell className="font-mono-plex font-bold">{s.preview}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="outline" size="sm" className="rounded-sm gap-1"
                    onClick={() => nextMut.mutate(s.id)}
                    data-testid={`seq-next-${s.key}`}
                  >
                    <Play size={12} /> {t("sequences.test_next")}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

function CreateSequenceDialog({ onSubmit, loading }) {
  const { t } = useTranslation();
  const [key, setKey] = useState(""); const [label, setLabel] = useState("");
  const [prefix, setPrefix] = useState(""); const [padding, setPadding] = useState(5);
  const [yr, setYr] = useState(true);
  const submit = (e) => { e.preventDefault(); onSubmit({ key: key.trim(), label, prefix, padding: Number(padding), year_reset: yr }); };
  return (
    <DialogContent className="rounded-sm" data-testid="create-sequence-dialog">
      <DialogHeader><DialogTitle className="font-display tracking-tight">{t("sequences.add")}</DialogTitle><DialogDescription>Configura una nuova numerazione progressiva.</DialogDescription></DialogHeader>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="overline">{t("sequences.key")}</Label>
            <Input value={key} required onChange={(e) => setKey(e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="cs-key" />
          </div>
          <div className="space-y-1.5">
            <Label className="overline">{t("sequences.label")}</Label>
            <Input value={label} required onChange={(e) => setLabel(e.target.value)} className="rounded-sm h-10" data-testid="cs-label" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="overline">{t("sequences.prefix")}</Label>
            <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} className="rounded-sm h-10 font-mono-plex" data-testid="cs-prefix" />
          </div>
          <div className="space-y-1.5">
            <Label className="overline">{t("sequences.padding")}</Label>
            <Input type="number" min={1} max={10} value={padding} onChange={(e) => setPadding(e.target.value)} className="rounded-sm h-10" data-testid="cs-padding" />
          </div>
        </div>
        <label className="flex items-center gap-3">
          <Switch checked={yr} onCheckedChange={setYr} data-testid="cs-yearreset" />
          <span className="text-sm">{t("sequences.year_reset")}</span>
        </label>
        <DialogFooter><Button type="submit" disabled={loading} className="rounded-sm" data-testid="cs-submit">{loading ? t("common.loading") : t("common.create")}</Button></DialogFooter>
      </form>
    </DialogContent>
  );
}
