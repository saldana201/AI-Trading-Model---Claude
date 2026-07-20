// Phase 9 — Confluence data + auth providers for Refine.
//
// Hand-written instead of @refinedev/simple-rest so the entire HTTP contract
// is inspectable in one file and there's no axios dependency. Same glass-box
// philosophy as the engines: you can read exactly what goes over the wire.

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const KEY = "confluence_api_key";

export const getKey = () =>
  typeof window === "undefined" ? null : window.localStorage.getItem(KEY);
const setKey = (k) => window.localStorage.setItem(KEY, k);
const clearKey = () => window.localStorage.removeItem(KEY);

function headers() {
  const h = { "Content-Type": "application/json" };
  const k = getKey();
  if (k) h["X-API-Key"] = k;
  return h;
}

async function request(path, init = {}) {
  const res = await fetch(`${API}${path}`, { ...init, headers: headers() });
  if (res.status === 401) {
    clearKey();
    throw { message: "Unauthorized", statusCode: 401 };
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    throw { message: String(detail), statusCode: res.status };
  }
  const total = res.headers.get("X-Total-Count");
  const data = res.status === 204 ? null : await res.json();
  return { data, total: total ? Number(total) : undefined };
}

/* ---------------- data provider ---------------- */

export const dataProvider = {
  getApiUrl: () => API,

  getList: async ({ resource, pagination, sorters, filters }) => {
    const q = new URLSearchParams();
    const { currentPage = 1, pageSize = 25, mode } = pagination || {};
    if (mode !== "off") {
      q.set("_start", String((currentPage - 1) * pageSize));
      q.set("_end", String(currentPage * pageSize));
    }
    if (sorters?.length) {
      q.set("_sort", sorters[0].field);
      q.set("_order", sorters[0].order);
    }
    (filters || []).forEach((f) => {
      if (f.field && f.value !== undefined && f.value !== "")
        q.set(f.field, String(f.value));
    });
    const { data, total } = await request(`/api/resources/${resource}?${q}`);
    return { data, total: total ?? data.length };
  },

  getOne: async ({ resource, id }) => {
    const { data } = await request(`/api/resources/${resource}/${id}`);
    return { data };
  },

  create: async ({ resource, variables }) => {
    const { data } = await request(`/api/resources/${resource}`, {
      method: "POST",
      body: JSON.stringify(variables),
    });
    return { data };
  },

  update: async ({ resource, id, variables }) => {
    const { data } = await request(`/api/resources/${resource}/${id}`, {
      method: "PATCH",
      body: JSON.stringify(variables),
    });
    return { data };
  },

  deleteOne: async ({ resource, id }) => {
    const { data } = await request(`/api/resources/${resource}/${id}`, {
      method: "DELETE",
    });
    return { data };
  },

  getMany: async ({ resource, ids }) => {
    const rows = await Promise.all(
      ids.map((id) => request(`/api/resources/${resource}/${id}`))
    );
    return { data: rows.map((r) => r.data) };
  },
};

/* ---------------- auth provider ---------------- */

export const authProvider = {
  // If the gateway reports auth disabled, skip the login flow entirely.
  login: async ({ apiKey }) => {
    setKey(apiKey || "");
    try {
      await request("/api/resources/trades?_start=0&_end=1");
      return { success: true, redirectTo: "/admin" };
    } catch (e) {
      clearKey();
      return {
        success: false,
        error: { name: "Login failed", message: e.message || "Invalid API key" },
      };
    }
  },

  logout: async () => {
    clearKey();
    return { success: true, redirectTo: "/admin/login" };
  },

  check: async () => {
    try {
      const res = await fetch(`${API}/api/health`);
      const health = await res.json();
      if (health.auth === "disabled") return { authenticated: true };
    } catch {
      // gateway unreachable — let the resource call surface the real error
    }
    return getKey()
      ? { authenticated: true }
      : { authenticated: false, redirectTo: "/admin/login" };
  },

  onError: async (error) => {
    if (error?.statusCode === 401)
      return { logout: true, redirectTo: "/admin/login" };
    return {};
  },

  getIdentity: async () => (getKey() ? { name: "operator" } : null),
};
