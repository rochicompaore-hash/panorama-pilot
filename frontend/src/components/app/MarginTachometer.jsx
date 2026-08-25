/**
 * MarginTachometer — SVG semicircular gauge (msg 392 §13).
 *
 * Scale: 0 → 40% (values above show numerically but the needle caps at 40%).
 * Zones (color-coded, in order from left to right / low → high margin):
 *   0–7.99   CRITICO      hsl(0 72% 51%)   red
 *   8–14.99  SCARSO       hsl(30 90% 55%)  orange
 *   15–19.99 SUFFICIENTE  hsl(45 92% 55%)  amber
 *   20–29.99 BUONO        hsl(140 55% 45%) green
 *   30+      OTTIMO       hsl(200 82% 45%) blue
 *
 * All arc math is pure SVG — no external dep. Needle position is % of scale.
 * Component is view-only; policy lives in the backend.
 */
import React from "react";

const SCALE_MAX = 40; // visual max (§13 leggibilità 30 vs 40)
const R = 90;         // radius
const CX = 110;       // svg center
const CY = 110;
const STROKE = 22;

const BANDS = [
  { code: "CRITICO",     label: "CRITICO",     from: 0,   to: 8,   color: "hsl(0 72% 51%)" },
  { code: "SCARSO",      label: "SCARSO",      from: 8,   to: 15,  color: "hsl(30 90% 55%)" },
  { code: "SUFFICIENTE", label: "SUFFICIENTE", from: 15,  to: 20,  color: "hsl(45 92% 55%)" },
  { code: "BUONO",       label: "BUONO",       from: 20,  to: 30,  color: "hsl(140 55% 45%)" },
  { code: "OTTIMO",      label: "OTTIMO",      from: 30,  to: SCALE_MAX, color: "hsl(200 82% 45%)" },
];

function pctToAngle(pct) {
  // Semicircle 180° starting at 180° (left) to 360° (right).
  const clamped = Math.max(0, Math.min(SCALE_MAX, pct));
  const ratio = clamped / SCALE_MAX;
  return 180 + ratio * 180;
}

function polar(angleDeg, radius) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CX + radius * Math.cos(rad), y: CY + radius * Math.sin(rad) };
}

function arcPath(fromPct, toPct, radius = R) {
  const a1 = pctToAngle(fromPct);
  const a2 = pctToAngle(toPct);
  const p1 = polar(a1, radius);
  const p2 = polar(a2, radius);
  const largeArc = a2 - a1 > 180 ? 1 : 0;
  return `M ${p1.x} ${p1.y} A ${radius} ${radius} 0 ${largeArc} 1 ${p2.x} ${p2.y}`;
}

export function MarginTachometer({ marginPct, band, testid = "margin-tachometer" }) {
  const num = typeof marginPct === "number" ? marginPct : null;
  const displayPct = num == null ? null : num;
  const needleAngle = num == null ? pctToAngle(0) : pctToAngle(num);
  const needleTip = polar(needleAngle, R - 6);
  const activeBand = BANDS.find((b) => b.code === band);

  return (
    <div className="flex flex-col items-center" data-testid={testid}>
      <svg viewBox="0 0 220 140" className="w-full max-w-[280px]" role="img" aria-label={`Marginalità ${displayPct ?? "n/d"}%`}>
        {/* Track */}
        {BANDS.map((b) => (
          <path
            key={b.code}
            d={arcPath(b.from, b.to)}
            fill="none"
            stroke={b.color}
            strokeWidth={STROKE}
            strokeLinecap="butt"
            opacity={activeBand && activeBand.code !== b.code ? 0.28 : 0.92}
            data-testid={`tachometer-band-${b.code}`}
          />
        ))}
        {/* Tick labels at band boundaries */}
        {[0, 8, 15, 20, 30, SCALE_MAX].map((t) => {
          const p = polar(pctToAngle(t), R + 16);
          return (
            <text key={t} x={p.x} y={p.y} textAnchor="middle" alignmentBaseline="middle"
                  className="fill-muted-foreground" style={{ fontSize: 9, fontFamily: "ui-monospace, monospace" }}>
              {t}
              {t === SCALE_MAX ? "+" : ""}
            </text>
          );
        })}
        {/* Needle */}
        {num != null && (
          <>
            <line x1={CX} y1={CY} x2={needleTip.x} y2={needleTip.y}
                  stroke="hsl(var(--foreground))" strokeWidth="3" strokeLinecap="round" />
            <circle cx={CX} cy={CY} r="6" fill="hsl(var(--foreground))" />
          </>
        )}
      </svg>
      {/* Numeric readout */}
      <div className="text-center mt-1" data-testid="tachometer-readout">
        <div className="text-4xl font-black font-display leading-none" data-testid="tachometer-margin-pct">
          {displayPct == null ? "—" : `${displayPct.toFixed(2).replace(".", ",")} %`}
        </div>
        {activeBand ? (
          <div className="mt-1 inline-flex items-center gap-2 rounded-sm px-2 py-0.5"
               style={{ backgroundColor: `${activeBand.color}20`, color: activeBand.color }}
               data-testid={`tachometer-band-label-${activeBand.code}`}>
            <span className="text-xs font-bold tracking-wider">{activeBand.label}</span>
          </div>
        ) : (
          <div className="mt-1 text-xs text-muted-foreground">Dati insufficienti</div>
        )}
      </div>
    </div>
  );
}

export default MarginTachometer;
