/**
 * CommissionTachometer — gauge 0 → 15% della COMMISSIONE PREVISTA (msg 801).
 * Valore autoritativo: ACTUAL_COMMISSION_RATE dal backend. NON rappresenta il margine aziendale.
 */
import React from "react";

const SCALE_MAX = 15;
const R = 90, CX = 110, CY = 110, STROKE = 22;

const ZONES = [
  { code: "NONE",   label: "NESSUNA COMMISSIONE", from: 0,  to: 3,  color: "hsl(215 15% 55%)" },
  { code: "LOW",    label: "FASCIA BASSA",        from: 3,  to: 8,  color: "hsl(215 40% 60%)" },
  { code: "MEDIUM", label: "FASCIA MEDIA",        from: 8,  to: 12, color: "hsl(215 60% 50%)" },
  { code: "HIGH",   label: "FASCIA ALTA",         from: 12, to: SCALE_MAX, color: "hsl(215 82% 40%)" },
];

function zoneFor(pct) {
  if (pct == null) return null;
  if (pct <= 0) return ZONES[0];
  if (pct < 8) return ZONES[1];
  if (pct < 12) return ZONES[2];
  return ZONES[3];
}
function pctToAngle(pct) { return 180 + (Math.max(0, Math.min(SCALE_MAX, pct)) / SCALE_MAX) * 180; }
function polar(a, r) { const rad = (a * Math.PI) / 180; return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) }; }
function arcPath(f, t) {
  const p1 = polar(pctToAngle(f), R), p2 = polar(pctToAngle(t), R);
  return `M ${p1.x} ${p1.y} A ${R} ${R} 0 0 1 ${p2.x} ${p2.y}`;
}

export function CommissionTachometer({ ratePct, testid = "commission-tachometer" }) {
  const num = typeof ratePct === "number" ? ratePct : null;
  const tip = polar(pctToAngle(num ?? 0), R - 6);
  const zone = zoneFor(num);
  return (
    <div className="flex flex-col items-center" data-testid={testid}>
      <svg viewBox="0 0 220 140" className="w-full max-w-[260px]" role="img" aria-label={`Commissione prevista ${num ?? "n/d"}%`}>
        {ZONES.map((z) => (
          <path key={z.code} d={arcPath(z.from, z.to)} fill="none" stroke={z.color} strokeWidth={STROKE}
                opacity={zone && zone.code !== z.code ? 0.25 : 0.9} data-testid={`commission-zone-${z.code}`} />
        ))}
        {[0, 3, 5, 8, 10, 12, 15].map((t) => {
          const p = polar(pctToAngle(t), R + 16);
          return <text key={t} x={p.x} y={p.y} textAnchor="middle" alignmentBaseline="middle" className="fill-muted-foreground" style={{ fontSize: 9, fontFamily: "ui-monospace, monospace" }}>{t}</text>;
        })}
        {num != null && (<>
          <line x1={CX} y1={CY} x2={tip.x} y2={tip.y} stroke="hsl(var(--foreground))" strokeWidth="3" strokeLinecap="round" />
          <circle cx={CX} cy={CY} r="6" fill="hsl(var(--foreground))" />
        </>)}
      </svg>
      <div className="text-center mt-1">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Commissione prevista</div>
        <div className="text-4xl font-black font-display leading-none" data-testid="commission-tachometer-pct">
          {num == null ? "—" : `${num.toFixed(2).replace(".", ",")} %`}
        </div>
        {zone && (
          <div className="mt-1 inline-flex rounded-sm px-2 py-0.5 text-xs font-bold tracking-wider" style={{ backgroundColor: `${zone.color}20`, color: zone.color }} data-testid={`commission-zone-label-${zone.code}`}>
            {zone.label}
          </div>
        )}
      </div>
    </div>
  );
}

export default CommissionTachometer;
