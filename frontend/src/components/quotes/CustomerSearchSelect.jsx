import React, { useEffect, useRef, useState } from "react";
import { api, formatApiError } from "@/api/client";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MagnifyingGlass, X, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { customerDisplayName } from "@/components/customers/CustomerTypeBadge";

const maskPhone = (p) => (p ? String(p).replace(/\s/g, "").slice(0, 3) + "•••••••" : null);
const maskVat = (v) => (v ? "P.IVA ••••••" + String(v).slice(-3) : null);
const cityOf = (c) => c.address?.city || c.city || c.billing_address?.city || null;

export function CustomerSearchSelect({ value, onChange, placeholder = "Cerca cliente…", allowClear = false, compact = false, testid = "customer-search" }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const timer = useRef();

  useEffect(() => {
    if (!open) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.get("/customers", { params: { q: q.trim() || undefined, limit: 20 } });
        setItems(data.items || []);
      } catch { setItems([]); } finally { setLoading(false); }
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q, open]);

  if (value && !open) {
    return (
      <div className={`flex items-center justify-between rounded-sm border px-3 ${compact ? "h-10" : "py-2"} text-sm`} data-testid={`${testid}-selected`}>
        <span className="truncate"><b>{customerDisplayName(value)}</b>{value.customer_number ? <span className="text-muted-foreground"> · {value.customer_number}</span> : null} <span className="text-emerald-700">✓</span></span>
        <div className="flex gap-1 shrink-0">
          <Button type="button" size="sm" variant="ghost" className="h-7 rounded-sm" onClick={() => { setOpen(true); setQ(""); }} data-testid={`${testid}-change`}>Cambia</Button>
          {allowClear && <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 rounded-sm" onClick={() => onChange(null)} data-testid={`${testid}-clear`}><X size={14} /></Button>}
        </div>
      </div>
    );
  }

  return (
    <div className="relative" data-testid={testid}>
      <div className="relative">
        <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
               placeholder={placeholder} className="rounded-sm h-10 pl-9" data-testid={`${testid}-input`} autoComplete="off" />
      </div>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-sm border bg-background shadow-lg max-h-72 overflow-y-auto" data-testid={`${testid}-results`}>
          {loading && <div className="px-3 py-2 text-xs text-muted-foreground">Ricerca…</div>}
          {!loading && items.map((c) => (
            <button type="button" key={c.id} className="w-full text-left px-3 py-2 hover:bg-accent border-b last:border-0 text-sm"
                    onClick={() => { onChange(c); setOpen(false); setQ(""); }} data-testid={`${testid}-result-${c.id}`}>
              <div className="font-medium">{customerDisplayName(c)}</div>
              <div className="text-xs text-muted-foreground flex gap-2 flex-wrap">
                {c.customer_number && <span>{c.customer_number}</span>}
                {cityOf(c) && <span>{cityOf(c)}</span>}
                {c.vat_number ? <span>{maskVat(c.vat_number)}</span> : c.phone ? <span>{maskPhone(c.phone)}</span> : null}
              </div>
            </button>
          ))}
          {!loading && items.length === 0 && (
            <div className="px-3 py-3 text-sm" data-testid={`${testid}-empty`}>
              <div className="text-muted-foreground">Nessun cliente trovato</div>
              {!creating && <Button type="button" size="sm" className="rounded-sm mt-2 gap-1" onClick={() => setCreating(true)} data-testid={`${testid}-create-btn`}><Plus size={14} /> Crea nuovo cliente</Button>}
            </div>
          )}
          {creating && <InlineCustomerCreate initialName={q} onCreated={(c) => { setCreating(false); onChange(c); setOpen(false); setQ(""); }} onCancel={() => setCreating(false)} testid={testid} />}
          <div className="flex justify-end border-t px-2 py-1"><Button type="button" size="sm" variant="ghost" className="h-7 rounded-sm" onClick={() => setOpen(false)}>Chiudi</Button></div>
        </div>
      )}
    </div>
  );
}

function InlineCustomerCreate({ initialName, onCreated, onCancel, testid }) {
  const parts = (initialName || "").trim().split(/\s+/);
  const [type, setType] = useState("private");
  const [f, setF] = useState({ first_name: parts[0] || "", last_name: parts.slice(1).join(" "), company_name: initialName || "", phone: "", email: "" });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const payload = type === "company"
        ? { customer_type: "company", company_name: f.company_name, phone: f.phone || undefined, email: f.email || undefined }
        : { customer_type: "private", first_name: f.first_name, last_name: f.last_name, phone: f.phone || undefined, email: f.email || undefined };
      const { data } = await api.post("/customers", payload);
      toast.success("Cliente creato");
      onCreated(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || e.message); } finally { setBusy(false); }
  };
  return (
    <div className="border-t p-3 space-y-2 text-sm" data-testid={`${testid}-create-form`}>
      <Select value={type} onValueChange={setType}>
        <SelectTrigger className="rounded-sm h-9" data-testid={`${testid}-create-type`}><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="private">Privato</SelectItem><SelectItem value="company">Azienda</SelectItem></SelectContent>
      </Select>
      {type === "company" ? (
        <Input placeholder="Ragione sociale *" value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} className="rounded-sm h-9" data-testid={`${testid}-create-company`} />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="Nome *" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} className="rounded-sm h-9" data-testid={`${testid}-create-first`} />
          <Input placeholder="Cognome *" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} className="rounded-sm h-9" data-testid={`${testid}-create-last`} />
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Input placeholder="Telefono" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} className="rounded-sm h-9" data-testid={`${testid}-create-phone`} />
        <Input placeholder="Email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} className="rounded-sm h-9" data-testid={`${testid}-create-email`} />
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="outline" className="rounded-sm h-8" onClick={onCancel}>Annulla</Button>
        <Button type="button" size="sm" className="rounded-sm h-8" disabled={busy} onClick={save} data-testid={`${testid}-create-save`}>Crea e seleziona</Button>
      </div>
    </div>
  );
}

export default CustomerSearchSelect;
