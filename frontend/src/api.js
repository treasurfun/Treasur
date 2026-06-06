// Thin API client. All calls go to /api/* which Netlify (_redirects) or the
// Vite dev proxy forwards to the FastAPI backend.

const TOKEN_KEY = "voult_token";

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t) {
  if (t) sessionStorage.setItem(TOKEN_KEY, t);
  else sessionStorage.removeItem(TOKEN_KEY);
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  login: (wallet, password) =>
    request("/auth/login", { method: "POST", body: { wallet, password }, auth: false }),
  register: (name, wallet, password) =>
    request("/auth/register", { method: "POST", body: { name, wallet, password }, auth: false }),
  assets: () => request("/assets", { auth: false }),
  createLaunch: (config) =>
    request("/launches", { method: "POST", body: { config } }),
  startLaunch: (id) => request(`/launches/${id}/start`, { method: "POST" }),
  getLaunch: (id) => request(`/launches/${id}`),
  myLaunches: () => request("/launches"),
  verify: (mint) => request(`/verify/${mint}`, { auth: false }),
  cashbackStatus: (id) => request(`/launches/${id}/cashback`),
  claimCashback: (id, asset) => request(`/launches/${id}/claim`, { method: "POST", body: { asset } }),
  me: () => request("/me"),
  feed: () => request("/feed", { auth: false }),
};
