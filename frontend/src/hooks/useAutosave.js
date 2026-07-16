/**
 * useAutosave — debounced autosave with concurrency + out-of-order protection.
 *
 * Usage:
 *   const autosave = useAutosave({
 *     entityId: quoteId,
 *     enabled: editable,
 *     endpoint: `/quotes/${quoteId}/autosave`,
 *     getVersion: () => quote.version,
 *     onSuccess: ({version, updated_at}) => { ... },
 *     onConflict: (detail, fields) => conflict.open(detail, fields, {...}),
 *   });
 *
 *   const patchField = (name, value) => autosave.schedule({ [name]: value });
 *
 *   <AutosaveIndicator state={autosave.state} lastSavedAt={autosave.lastSavedAt} onRetry={autosave.retry} />
 */
import React from "react";
import { api } from "@/api/client";

const DEBOUNCE_MS = 800;

export function useAutosave({
  endpoint,
  enabled = true,
  getVersion,
  onSuccess,
  onConflict,
  onError,
  minGapMs = 300,
}) {
  const [state, setState] = React.useState("idle"); // idle | dirty | saving | saved | error | conflict
  const [lastSavedAt, setLastSavedAt] = React.useState(null);
  const [lastError, setLastError] = React.useState(null);

  const pending = React.useRef({}); // accumulated fields to save
  const timer = React.useRef(null);
  const requestSeq = React.useRef(0);
  const inFlight = React.useRef(null); // AbortController

  const flush = React.useCallback(async () => {
    if (!enabled) return;
    const fields = { ...pending.current };
    if (Object.keys(fields).length === 0) return;
    pending.current = {};
    const rid = ++requestSeq.current;
    setState("saving");
    setLastError(null);
    if (inFlight.current) inFlight.current.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    try {
      const res = await api.post(
        endpoint,
        { version: getVersion() || 1, fields, request_id: String(rid) },
        { signal: controller.signal }
      );
      // Out-of-order guard
      if (Number(res.data.request_id) !== rid) return;
      setLastSavedAt(new Date());
      setState("saved");
      onSuccess?.(res.data);
    } catch (e) {
      if (e.name === "CanceledError" || e.code === "ERR_CANCELED") return;
      if (e.response?.status === 409) {
        setState("conflict");
        onConflict?.(e.response.data.detail, fields);
        return;
      }
      if (e.response?.status === 400 && /consolidato/i.test(e.response?.data?.detail || "")) {
        // Silent: doc no longer editable; do not spam errors
        setState("idle");
        return;
      }
      setLastError(e.response?.data?.detail || e.message || "Errore");
      setState("error");
      onError?.(e);
      // Restore pending so retry works
      pending.current = { ...fields, ...pending.current };
    }
  }, [endpoint, enabled, getVersion, onSuccess, onConflict, onError]);

  const schedule = React.useCallback((fields) => {
    if (!enabled) return;
    pending.current = { ...pending.current, ...fields };
    setState("dirty");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, DEBOUNCE_MS);
  }, [enabled, flush]);

  const flushNow = React.useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    return flush();
  }, [flush]);

  const retry = React.useCallback(() => flushNow(), [flushNow]);

  // beforeunload guard when dirty
  React.useEffect(() => {
    const handler = (e) => {
      if (state === "dirty" || state === "saving" || state === "error") {
        e.preventDefault();
        e.returnValue = "Ci sono modifiche non salvate. Vuoi davvero uscire?";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [state]);

  // Flush on unmount if dirty
  React.useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
      if (Object.keys(pending.current).length > 0) {
        // Fire-and-forget final flush
        const rid = ++requestSeq.current;
        api.post(endpoint, {
          version: getVersion() || 1,
          fields: pending.current,
          request_id: String(rid),
        }).catch(() => {});
      }
    };
    // eslint-disable-next-line
  }, []);

  return {
    schedule, flushNow, retry,
    state, lastSavedAt, lastError,
    hasPending: () => Object.keys(pending.current).length > 0,
  };
}
