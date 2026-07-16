import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, formatApiError } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Pencil, Trash, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const CATEGORIES = [
  "misure", "posa", "opere_murarie", "smaltimento", "elettricita",
  "accessibilita", "ponteggi", "tempistiche", "pagamenti", "garanzia",
  "detrazioni", "immagini", "variazioni", "annullamento", "privacy", "generale",
];

export default function ClausesPage() {
  const { has } = useAuth();
  const canManage = has("quotes.manage_clauses");
  const qc = useQueryClient();
  const [filterCat, setFilterCat] = React.useState("all");
  const [editing, setEditing] = React.useState(null);

  const { data: resp } = useQuery({
    queryKey: ["clauses-admin"],
    queryFn: async () => (await api.get(`/clauses`)).data,
  });
  const clauses = (resp?.items || []).filter((c) => filterCat === "all" || c.category === filterCat);

  const save = useMutation({
    mutationFn: async (body) => {
      if (body.id) {
        const { id, version, ...rest } = body;
        return (await api.patch(`/clauses/${id}`, rest, { headers: { "If-Match": String(version || 1) } })).data;
      }
      return (await api.post(`/clauses`, body)).data;
    },
    onSuccess: () => { toast.success("Clausola salvata"); qc.invalidateQueries({ queryKey: ["clauses-admin"] }); setEditing(null); },
    onError: (e) => toast.error(formatApiError(e.response?.data?.detail)),
  });
  const del = useMutation({
    mutationFn: async (cid) => (await api.delete(`/clauses/${cid}`)).data,
    onSuccess: () => { toast.success("Clausola eliminata"); qc.invalidateQueries({ queryKey: ["clauses-admin"] }); },
  });

  return (
    <div className="space-y-6" data-testid="clauses-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="overline">Amministrazione</div>
          <h1 className="mt-1 font-display text-3xl font-black tracking-tight">Clausole contrattuali</h1>
          <p className="text-sm text-muted-foreground mt-1">Libreria modulare. Ogni clausola è versionata; modificarne una preserva il testo storico nei PDF già emessi.</p>
        </div>
        {canManage && (
          <Button className="rounded-sm" onClick={() => setEditing({ code: "", title: "", text: "", category: "generale", language: "it", mandatory: false, order_index: 100 })} data-testid="clause-new"><Plus size={14} className="mr-1" /> Nuova clausola</Button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Select value={filterCat} onValueChange={setFilterCat}>
          <SelectTrigger className="rounded-sm w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tutte le categorie</SelectItem>
            {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
        <Badge variant="outline" className="rounded-sm font-mono-plex">{clauses.length} clausole</Badge>
      </div>

      <Card className="rounded-sm border-border p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="overline">Codice</TableHead>
              <TableHead className="overline">Titolo</TableHead>
              <TableHead className="overline">Categoria</TableHead>
              <TableHead className="overline">Testo</TableHead>
              <TableHead className="overline">Obbl.</TableHead>
              <TableHead className="overline">Ver.</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {clauses.map((c) => (
              <TableRow key={c.id} data-testid={`clause-${c.code}`}>
                <TableCell className="font-mono-plex text-[10px]">{c.code}</TableCell>
                <TableCell className="text-sm font-bold">{c.title}</TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm text-[10px]">{c.category}</Badge></TableCell>
                <TableCell className="text-xs max-w-md truncate" title={c.text}>{c.text}</TableCell>
                <TableCell>{c.mandatory && <ShieldCheck size={14} className="text-emerald-600" />}</TableCell>
                <TableCell className="font-mono-plex text-xs">v.{c.version}</TableCell>
                <TableCell>
                  {canManage && (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(c)} data-testid={`clause-edit-${c.code}`}><Pencil size={12} /></Button>
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => { if (confirm(`Eliminare ${c.code}?`)) del.mutate(c.id); }}><Trash size={12} /></Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {editing && (
        <Dialog open={true} onOpenChange={(v) => !v && setEditing(null)}>
          <DialogContent className="max-w-2xl rounded-sm">
            <DialogHeader>
              <DialogTitle>{editing.id ? `Modifica ${editing.code}` : "Nuova clausola"}</DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><Label>Codice</Label><Input value={editing.code} onChange={(e) => setEditing({ ...editing, code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_") })} disabled={!!editing.id} className="rounded-sm font-mono-plex" /></div>
              <div><Label>Categoria</Label><Select value={editing.category} onValueChange={(v) => setEditing({ ...editing, category: v })}><SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger><SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
              <div className="col-span-2"><Label>Titolo</Label><Input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} className="rounded-sm" /></div>
              <div className="col-span-2"><Label>Testo</Label><Textarea rows={8} value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} className="rounded-sm" data-testid="clause-text" /></div>
              <div><Label>Ordine</Label><Input type="number" value={editing.order_index || 100} onChange={(e) => setEditing({ ...editing, order_index: Number(e.target.value) })} className="rounded-sm font-mono-plex" /></div>
              <div className="flex items-end gap-2"><Switch checked={!!editing.mandatory} onCheckedChange={(v) => setEditing({ ...editing, mandatory: v })} data-testid="clause-mandatory" /> Obbligatoria</div>
            </div>
            <DialogFooter>
              <Button variant="outline" className="rounded-sm" onClick={() => setEditing(null)}>Annulla</Button>
              <Button className="rounded-sm" onClick={() => save.mutate(editing)} disabled={!editing.code || !editing.title || !editing.text} data-testid="clause-save">Salva</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
