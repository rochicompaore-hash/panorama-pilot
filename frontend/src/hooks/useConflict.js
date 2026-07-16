/** Hook for wrapping mutations with optimistic concurrency control.
 *
 * Usage:
 *   const conflict = useConflict();
 *   const patch = async (fields) => {
 *     try {
 *       await api.patch(`/quotes/${id}`, fields, { headers: { "If-Match": version } });
 *     } catch (e) {
 *       if (e.response?.status === 409) return conflict.open(e.response.data.detail, fields, {...actions});
 *       throw e;
 *     }
 *   };
 *   <ConflictModal ...conflict.modalProps />
 */
import React from "react";

export function useConflict() {
  const [state, setState] = React.useState({ open: false, conflict: null, localData: null, actions: null });

  const open = (conflictDetail, localData, actions) => {
    setState({ open: true, conflict: conflictDetail, localData, actions: actions || {} });
  };
  const close = () => setState({ open: false, conflict: null, localData: null, actions: null });

  return {
    open,
    close,
    modalProps: {
      open: state.open,
      onOpenChange: (v) => { if (!v) close(); },
      conflict: state.conflict,
      localData: state.localData,
      canForceOverride: state.actions?.canForceOverride,
      allowForce: state.actions?.allowForce !== false,
      onReload: state.actions?.onReload,
      onKeepCopy: state.actions?.onKeepCopy,
      onForce: state.actions?.onForce,
    },
  };
}

/** Extract the version from a fetched entity. Falls back to 1. */
export const getVersion = (doc) => (doc && typeof doc.version === "number" ? doc.version : 1);

/** Convenience: build axios config with If-Match header. */
export const withVersion = (version) => ({ headers: { "If-Match": String(version ?? 1) } });

/** Convenience: build config with force+reason. */
export const withForce = (reason) => ({
  params: { force: true },
  headers: { "X-Force-Reason": reason },
});
