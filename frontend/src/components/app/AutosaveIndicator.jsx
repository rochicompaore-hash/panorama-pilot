import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check, CloudArrowUp, WarningCircle, ArrowClockwise, Circle } from "@phosphor-icons/react";

const STATES = {
  idle:     { label: "Nessuna modifica",  cls: "bg-secondary text-muted-foreground",       Icon: Circle },
  dirty:    { label: "Modifiche in coda", cls: "bg-amber-500/15 text-amber-800",          Icon: Circle },
  saving:   { label: "Salvataggio…",      cls: "bg-blue-500/15 text-blue-800 animate-pulse", Icon: CloudArrowUp },
  saved:    { label: "Salvato",           cls: "bg-emerald-500/15 text-emerald-800",      Icon: Check },
  error:    { label: "Errore",            cls: "bg-red-500/15 text-red-800",              Icon: WarningCircle },
  conflict: { label: "Conflitto",         cls: "bg-orange-500/20 text-orange-800",        Icon: WarningCircle },
};

export function AutosaveIndicator({ state = "idle", lastSavedAt, lastError, onRetry, className = "" }) {
  const s = STATES[state] || STATES.idle;
  const { Icon } = s;
  const time = lastSavedAt ? new Date(lastSavedAt).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : null;
  return (
    <div className={`flex items-center gap-2 ${className}`} data-testid="autosave-indicator" data-state={state}>
      <Badge variant="outline" className={`rounded-sm text-[10px] font-mono-plex ${s.cls} border-0`} data-testid="autosave-badge">
        <Icon size={11} className="mr-1" /> {s.label}
        {state === "saved" && time && <span className="ml-1 opacity-70">{time}</span>}
      </Badge>
      {state === "error" && (
        <>
          <span className="text-[10px] text-destructive font-mono-plex truncate max-w-[240px]" title={lastError}>{lastError}</span>
          <Button size="sm" variant="outline" className="rounded-sm h-6 text-[10px]" onClick={onRetry} data-testid="autosave-retry">
            <ArrowClockwise size={11} className="mr-1" /> Riprova
          </Button>
        </>
      )}
    </div>
  );
}
