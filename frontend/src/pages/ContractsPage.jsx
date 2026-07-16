import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export default function ContractsPage() {
  const nav = useNavigate();
  const [contracts, setContracts] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [quotes, setQuotes] = useState([]);
  const [selectedQuote, setSelectedQuote] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => { load(); loadQuotes(); }, [statusFilter]);

  const load = async () => {
    const params = statusFilter && statusFilter !== "__all__" ? `?state=${statusFilter}` : "";
    try {
      const { data } = await api.get(`/contracts${params}`);
      setContracts(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error("Errore caricamento contratti");
    }
  };

  const loadQuotes = async () => {
    try {
      const { data } = await api.get("/quotes?limit=50");
      setQuotes((data.items || []).filter(q => ["sent", "accepted", "active", "approved"].includes(q.status)));
    } catch {}
  };

  const generateFromQuote = async () => {
    if (!selectedQuote) { toast.error("Seleziona un preventivo"); return; }
    try {
      const { data } = await api.post("/contracts/generate-from-quote", { quote_id: selectedQuote });
      toast.success(`Contratto ${data.number} creato`);
      setOpen(false);
      load();
      nav(`/contracts/${data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Errore generazione contratto");
    }
  };

  return (
    <div className="p-6 space-y-6" data-testid="contracts-page">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">Contratti</h1>
          <p className="text-sm text-muted-foreground mt-1">Gestione contratti generati da preventivi firmati/accettati</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button data-testid="btn-new-contract">+ Nuovo contratto da preventivo</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Genera contratto da preventivo</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Preventivo</Label>
                <Select value={selectedQuote} onValueChange={setSelectedQuote}>
                  <SelectTrigger data-testid="select-quote"><SelectValue placeholder="Scegli preventivo…"/></SelectTrigger>
                  <SelectContent>
                    {quotes.map(q => (
                      <SelectItem key={q.id} value={q.id}>{q.number} — {q.customer_name || q.customer_id} — {(q.total || 0).toFixed(2)}€</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={generateFromQuote} data-testid="btn-generate">Genera contratto</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Elenco ({total})</CardTitle>
          <div className="flex gap-2 mt-2">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-48" data-testid="filter-status"><SelectValue placeholder="Tutti gli stati"/></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Tutti</SelectItem>
                {["draft","ready_for_review","ready_for_signature","sent","viewed","signing","signed","rejected","expired","cancelled","superseded"].map(s => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Numero</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Preventivo</TableHead>
                <TableHead>Stato</TableHead>
                <TableHead>Totale</TableHead>
                <TableHead>Azioni</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contracts.map(c => (
                <TableRow key={c.id} data-testid={`contract-${c.id}`}>
                  <TableCell className="font-mono text-sm">{c.number}</TableCell>
                  <TableCell className="text-xs">{c.created_at ? new Date(c.created_at).toLocaleDateString("it-IT") : "-"}</TableCell>
                  <TableCell className="text-xs">{c.quote_snapshot?.customer?.name || c.customer_id?.slice(0,8) || "-"}</TableCell>
                  <TableCell className="text-xs">{c.quote_snapshot?.quote_number || c.quote_id?.slice(0,8)}</TableCell>
                  <TableCell><Badge variant={c.contract_status === "signed" ? "default" : "secondary"}>{c.contract_status}</Badge></TableCell>
                  <TableCell className="font-mono text-xs">{(c.quote_snapshot?.quote_totals?.total || 0).toFixed(2)} €</TableCell>
                  <TableCell>
                    <Button size="sm" variant="outline" onClick={() => nav(`/contracts/${c.id}`)}
                             data-testid={`btn-open-${c.id}`}>Apri</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
