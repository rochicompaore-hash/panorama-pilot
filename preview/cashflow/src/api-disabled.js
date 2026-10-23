// Preview-only import guard. It never emulates the production API or computes data.
// CashCommandCenterView does not invoke it; accidental use fails locally.
function disabledApi() {
  throw new Error("Questa anteprima usa soltanto i dati di prova inclusi nella build.");
}

export const api = {
  get: disabledApi,
  post: disabledApi,
  put: disabledApi,
  patch: disabledApi,
  delete: disabledApi,
};

export function formatApiError(detail) {
  return typeof detail === "string" ? detail : "API disabilitata nell’anteprima.";
}
