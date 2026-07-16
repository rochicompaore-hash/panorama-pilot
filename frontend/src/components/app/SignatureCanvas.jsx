/** Signature capture component using signature_pad. Returns { dataURL, strokeCount, canvasWidth, canvasHeight, durationMs }. */
import React, { useEffect, useRef, useState } from "react";
import SignaturePad from "signature_pad";
import { Button } from "@/components/ui/button";
import { Trash, ArrowClockwise } from "@phosphor-icons/react";

export default function SignatureCanvas({ onChange, disabled = false, brand = "#0F1720" }) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const padRef = useRef(null);
  const startedAtRef = useRef(null);
  const [hasSignature, setHasSignature] = useState(false);
  const [strokeCount, setStrokeCount] = useState(0);

  const resizeCanvas = React.useCallback(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const w = wrap.clientWidth;
    const h = 200;
    canvas.width = w * ratio;
    canvas.height = h * ratio;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
    if (padRef.current) padRef.current.clear();
  }, []);

  useEffect(() => {
    const pad = new SignaturePad(canvasRef.current, {
      minWidth: 0.6,
      maxWidth: 2.2,
      penColor: "#101828",
      backgroundColor: "rgba(0,0,0,0)",
      throttle: 16,
    });
    padRef.current = pad;
    resizeCanvas();

    const onBegin = () => {
      if (!startedAtRef.current) startedAtRef.current = Date.now();
    };
    const onEnd = () => {
      const data = pad.toData();
      const count = Array.isArray(data) ? data.length : 0;
      setStrokeCount(count);
      const has = !pad.isEmpty();
      setHasSignature(has);
      emit();
    };
    pad.addEventListener("beginStroke", onBegin);
    pad.addEventListener("endStroke", onEnd);

    const ro = new ResizeObserver(() => resizeCanvas());
    ro.observe(wrapRef.current);
    return () => {
      pad.removeEventListener("beginStroke", onBegin);
      pad.removeEventListener("endStroke", onEnd);
      ro.disconnect();
      pad.off();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (padRef.current) {
      if (disabled) padRef.current.off(); else padRef.current.on();
    }
  }, [disabled]);

  const emit = () => {
    const pad = padRef.current;
    if (!pad) return;
    if (pad.isEmpty()) {
      onChange?.(null);
      return;
    }
    const dataURL = pad.toDataURL("image/png");
    const durationMs = startedAtRef.current ? (Date.now() - startedAtRef.current) : 0;
    const cnv = canvasRef.current;
    onChange?.({
      data_url: dataURL,
      stroke_count: pad.toData().length,
      canvas_width: cnv.width,
      canvas_height: cnv.height,
      total_duration_ms: durationMs,
    });
  };

  const handleClear = () => {
    padRef.current?.clear();
    startedAtRef.current = null;
    setHasSignature(false);
    setStrokeCount(0);
    onChange?.(null);
  };

  const handleUndo = () => {
    const pad = padRef.current;
    if (!pad) return;
    const data = pad.toData();
    if (data.length > 0) {
      data.pop();
      pad.fromData(data);
      setStrokeCount(data.length);
      setHasSignature(data.length > 0);
      emit();
    }
  };

  return (
    <div className="space-y-2">
      <div
        ref={wrapRef}
        className="relative rounded-sm border-2 border-dashed bg-white select-none touch-none"
        style={{ borderColor: hasSignature ? brand : "#d0d5dd" }}
        data-testid="signature-canvas-wrap"
      >
        <canvas ref={canvasRef} className="block w-full rounded-sm cursor-crosshair" style={{ touchAction: "none" }} />
        {!hasSignature && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            Firma qui con il mouse, il dito o lo stilo
          </div>
        )}
      </div>
      <div className="flex justify-between items-center text-xs text-muted-foreground">
        <span data-testid="signature-strokes">Tratti: {strokeCount}</span>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" className="rounded-sm" onClick={handleUndo}
                  disabled={!hasSignature} data-testid="signature-undo">
            <ArrowClockwise size={14} className="mr-1" /> Annulla ultimo
          </Button>
          <Button type="button" variant="outline" size="sm" className="rounded-sm" onClick={handleClear}
                  disabled={!hasSignature} data-testid="signature-clear">
            <Trash size={14} className="mr-1" /> Cancella
          </Button>
        </div>
      </div>
    </div>
  );
}
