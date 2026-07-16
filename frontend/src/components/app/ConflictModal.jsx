import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, RefreshCw, Copy, ShieldAlert } from "lucide-react";

/** Modal shown when a 409 (version conflict) is caught.
 *
 * Props:
 *  - open, onOpenChange
 *  - conflict: { entity_type, expected_version, current_version, updated_by, updated_at, server_data }
 *  - localData: the local state the user tried to submit
 *  - canForceOverride: boolean (permission records.force_override)
 *  - allowForce: whether force is meaningful for this doc (not consolidated)
 *  - onReload: () => Promise — reload server version, discard local
 *  - onKeepCopy: () => Promise — duplicate/create new revision
 *  - onForce: (reason) => Promise — force overwrite (requires reason)
 */
export function ConflictModal({
  open, onOpenChange, conflict, localData,
  canForceOverride = false, allowForce = true,
  onReload, onKeepCopy, onForce,
}) {
  const [reason, setReason] = React.useState("");
  const [forcing, setForcing] = React.useState(false);

  const changedFields = React.useMemo(() => {
    if (!conflict) return [];
    const server = conflict.server_data || {};
    const local = localData || {};
    const keys = new Set([...Object.keys(local), ...Object.keys(server).filter((k) => k in local)]);
    const diffs = [];
    for (const k of keys) {
      const sv = server[k];
      const lv = local[k];
      const eq = JSON.stringify(sv) === JSON.stringify(lv);
      if (!eq) diffs.push({ field: k, server: sv, local: lv });
    }
    return diffs.slice(0, 12);
  }, [conflict, localData]);

  if (!conflict) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-sm" data-testid="conflict-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="text-amber-500" size={20} />
            Modifica in conflitto
          </DialogTitle>
          <DialogDescription>
            Un altro utente ha aggiornato questo record mentre stavi lavorando. Scegli come procedere per non perdere dati.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-sm border border-border p-3">
              <div className="overline mb-1">La tua versione</div>
              <div className="font-mono-plex">v.{conflict.expected_version}</div>
            </div>
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/5 p-3">
              <div className="overline mb-1">Versione sul server</div>
              <div className="font-mono-plex font-bold">v.{conflict.current_version}</div>
              {conflict.updated_at && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  {new Date(conflict.updated_at).toLocaleString("it-IT")}
                </div>
              )}
              {conflict.updated_by && (
                <div className="text-[10px] text-muted-foreground">Utente: {conflict.updated_by}</div>
              )}
            </div>
          </div>

          {changedFields.length > 0 && (
            <div className="rounded-sm border border-border">
              <div className="overline p-2 border-b bg-secondary/50">Campi diversi ({changedFields.length})</div>
              <div className="max-h-56 overflow-auto text-xs">
                {changedFields.map((d, i) => (
                  <div key={i} className="grid grid-cols-3 gap-2 p-2 border-b last:border-b-0">
                    <div className="font-mono-plex text-[11px] font-bold">{d.field}</div>
                    <div className="truncate"><Badge variant="outline" className="rounded-sm text-[10px] mr-1">tu</Badge><span className="font-mono-plex">{JSON.stringify(d.local)}</span></div>
                    <div className="truncate"><Badge variant="outline" className="rounded-sm text-[10px] mr-1 bg-amber-500/10">server</Badge><span className="font-mono-plex">{JSON.stringify(d.server)}</span></div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {canForceOverride && allowForce && (
            <div className="rounded-sm border border-destructive/40 p-3 space-y-2">
              <div className="text-xs flex items-center gap-2 text-destructive font-bold">
                <ShieldAlert size={14} /> Sovrascrittura forzata (registrata in audit log)
              </div>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Motivazione obbligatoria (min. 10 caratteri)…"
                rows={2}
                className="rounded-sm text-xs"
                data-testid="conflict-force-reason"
              />
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 flex-wrap sm:flex-nowrap">
          <Button variant="outline" className="rounded-sm" onClick={async () => { await onReload?.(); onOpenChange(false); }} data-testid="conflict-reload">
            <RefreshCw size={14} className="mr-1" /> Ricarica versione aggiornata
          </Button>
          {onKeepCopy && (
            <Button variant="outline" className="rounded-sm" onClick={async () => { await onKeepCopy?.(); onOpenChange(false); }} data-testid="conflict-keep-copy">
              <Copy size={14} className="mr-1" /> Conserva una copia
            </Button>
          )}
          {canForceOverride && allowForce && (
            <Button
              variant="destructive"
              className="rounded-sm"
              disabled={forcing || reason.trim().length < 10}
              onClick={async () => {
                setForcing(true);
                try {
                  await onForce?.(reason);
                  onOpenChange(false);
                } finally { setForcing(false); }
              }}
              data-testid="conflict-force"
            >
              <ShieldAlert size={14} className="mr-1" /> Sovrascrivi con motivazione
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
