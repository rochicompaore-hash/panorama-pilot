import React from "react";
import { Badge } from "@/components/ui/badge";

/**
 * ProductVisualSVG — consuma il VisualSpec canonico prodotto dal backend
 * ({ spec, is_bicolor, svg_interior, svg_exterior }). Nessuna logica di ricostruzione lato client:
 * UI e PDF usano lo stesso SVG deterministico.
 */
export function ProductVisualSVG({ visual, size = 220, defaultView = "INTERIOR", showToggle = true, testid = "product-visual" }) {
  const [view, setView] = React.useState(defaultView);
  if (!visual?.svg_exterior) return null;
  const isWindow = ["WINDOW", "DOOR_WINDOW"].includes(visual.spec?.product_type);
  const svg = view === "INTERIOR" && isWindow ? visual.svg_interior : visual.svg_exterior;
  return (
    <div className="space-y-2" data-testid={testid} data-view={isWindow ? view : "EXTERIOR"} data-bicolor={visual.is_bicolor ? "true" : "false"}>
      {isWindow && showToggle && (
        <div className="flex items-center gap-1" data-testid={`${testid}-view-toggle`}>
          {[["INTERIOR", "Vista interna"], ["EXTERIOR", "Vista esterna"]].map(([v, l]) => (
            <button
              key={v} type="button" onClick={() => setView(v)}
              className={`text-[10px] px-2 py-1 rounded-sm border transition-colors ${view === v ? "bg-primary text-primary-foreground border-primary" : "border-border hover:border-primary/50"}`}
              data-testid={`${testid}-view-${v.toLowerCase()}`}
            >{l}</button>
          ))}
          {visual.is_bicolor && <Badge variant="outline" className="rounded-sm text-[9px] ml-auto" data-testid={`${testid}-bicolor-badge`}>BICOLORE</Badge>}
        </div>
      )}
      <div
        className="rounded-sm border border-border bg-white [&>svg]:w-full [&>svg]:h-auto"
        style={{ width: size, maxWidth: "100%" }}
        dangerouslySetInnerHTML={{ __html: svg }}
        data-testid={`${testid}-svg`}
      />
    </div>
  );
}

/** Miniatura compatta per tabelle (interna + esterna se bicolore). */
export function ProductVisualThumb({ visual, size = 56, testid = "product-visual-thumb" }) {
  if (!visual?.svg_exterior) return null;
  const isWindow = ["WINDOW", "DOOR_WINDOW"].includes(visual.spec?.product_type);
  const svgs = visual.is_bicolor ? [visual.svg_interior, visual.svg_exterior] : [isWindow ? visual.svg_interior : visual.svg_exterior];
  return (
    <div className="flex gap-1 shrink-0" data-testid={testid} data-bicolor={visual.is_bicolor ? "true" : "false"}>
      {svgs.map((s, i) => (
        <div key={i} className="rounded-sm border border-border bg-white [&>svg]:w-full [&>svg]:h-full" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: s }} />
      ))}
    </div>
  );
}
