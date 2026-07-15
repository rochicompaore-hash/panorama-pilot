import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// Attach bearer token as fallback (in case cookies not carried in cross-origin)
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("ie_access_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

let isRefreshing = false;
let pendingQueue = [];

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry && !original.url?.includes("/auth/")) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject, original });
        });
      }
      original._retry = true;
      isRefreshing = true;
      try {
        const rt = localStorage.getItem("ie_refresh_token");
        const res = await axios.post(
          `${API_BASE}/auth/refresh`,
          rt ? { refresh_token: rt } : {},
          { withCredentials: true }
        );
        if (res.data?.access_token) {
          localStorage.setItem("ie_access_token", res.data.access_token);
          localStorage.setItem("ie_refresh_token", res.data.refresh_token);
        }
        pendingQueue.forEach((p) => {
          p.original.headers.Authorization = `Bearer ${res.data.access_token}`;
          p.resolve(api(p.original));
        });
        pendingQueue = [];
        original.headers.Authorization = `Bearer ${res.data.access_token}`;
        return api(original);
      } catch (e) {
        pendingQueue.forEach((p) => p.reject(e));
        pendingQueue = [];
        localStorage.removeItem("ie_access_token");
        localStorage.removeItem("ie_refresh_token");
        window.location.assign("/login");
        return Promise.reject(e);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

export function formatApiError(detail) {
  if (detail == null) return "Si è verificato un errore. Riprova.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean)
      .join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
