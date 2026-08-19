import React from "react";
import { Badge } from "@/components/ui/badge";

export function CustomerTypeBadge({ type }) {
  const t = (type || "TO_CONFIRM").toUpperCase();
  if (t === "PRIVATE") {
    return (
      <Badge variant="outline" className="rounded-sm text-[10px] font-mono-plex" data-testid="badge-private">
        PRIVATO
      </Badge>
    );
  }
  if (t === "COMPANY") {
    return (
      <Badge variant="outline" className="rounded-sm text-[10px] font-mono-plex bg-blue-50 border-blue-200 text-blue-900" data-testid="badge-company">
        AZIENDA
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="rounded-sm text-[10px] font-mono-plex bg-amber-50 border-amber-300 text-amber-900" data-testid="badge-to-confirm">
      Da confermare
    </Badge>
  );
}

export function customerDisplayName(c) {
  if (!c) return "—";
  const nameParts = [c.first_name, c.last_name].filter(Boolean).join(" ").trim();
  if (c.customer_type === "COMPANY") return c.company_name || nameParts || "—";
  return nameParts || c.company_name || "—";
}
