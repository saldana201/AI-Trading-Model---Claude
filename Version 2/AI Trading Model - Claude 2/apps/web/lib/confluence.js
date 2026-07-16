"use client";
/**
 * Confluence providers for Refine — glass-box, dependency-free.
 *
 * dataProvider: a ~70-line fetch client speaking the gateway's resource
 * dialect (_start/_end, _sort/_order, field=value filters, X-Total-Count).
 * Written by hand instead of importing @refinedev/simple-rest so the whole
 * HTTP contract is visible in this file — same philosophy as the engines.
 *
 * authProvider: single-operator API key. The key is entered once on
 * /admin/login, held in localStorage, and sent as X-API-Key. A 401 anywhere
 * bounces back to login. If the gateway reports auth disabled (dev mode,
 * no CONFLUENCE_API_KEY set), login is waved through.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const KEY_STORAGE = "confluence_api_key";

export const getKey = () =>
  typeof window === "undefined" ? null : localStorage.getItem(KEY_STORAGE);

const headers = () => {
  const h = { "Content-Type": "application/json" };
  const key = getKey();
  if (key) h["X-API-Key"] = key;
  return h;
};

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: headers(),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const error = new Error(body || res.statusText);
    error.statusCode = res.status;
    throw error;
  }
  return res;
}

const enc = encodeURIComponent;

export const dataProvider = {
  getApiUrl: () => API_URL,

  getList: async ({ resource, pagination, sorters, filters }) => {
    const params = new URLSearchParams();
    const { currentPage = 1, pageSize = 25 } = pagination ?? {};
    params.set("_start", String((currentPage - 1) * pageSize));
    params.set("_end", String(currentPage * pageSize));
    if (sorters?.length) {
      params.set("_sort", sorters[0].field);
      params.set("_order", sorters[0].order);
    }
    (filters ?? []).forEach((f) => {
      if (f.field && f.value !== undefined && f.value !== "")
        params.set(f.field, String(f.value));
    });
    const res = await request(`/api/resources/${resource}?${params}`);
    return {
      data: await res.json(),
      total: Number(res.headers.get("x-total-count") ?? 0),
    };
  },

  getOne: async ({ resource, id }) => ({
    data: await (await request(`/api/resources/${resource}/${enc(id)}`)).json(),
  }),

  create: async ({ resource, variables }) => ({
    data: await (await request(`/api/resources/${resource}`, {
      method: "POST",
      body: JSON.stringify(variables),
    })).json(),
  }),

  update: async ({ resource, id, variables, meta }) => ({
    // watchlist replaces whole records (PUT); trades patch fields (PATCH)
    data: await (await request(`/api/resources/${resource}/${enc(id)}`, {
      method: meta?.method || (resource === "watchlist" ? "PUT" : "PATCH"),
      body: JSON.stringify(variables),
    })).json(),
  }),

  deleteOne: async ({ resource, id }) => ({
    data: await (await request(`/api/resources/${resource}/${enc(id)}`, {
      method: "DELETE",
    })).json(),
  }),
};

export const authProvider = {
  login: async ({ apiKey }) => {
    localStorage.setItem(KEY_STORAGE, apiKey ?? "");
    try {
      await request("/api/resources/watchlist?_start=0&_end=1");
      return { success: true, redirectTo: "/admin" };
    } catch (e) {
      localStorage.removeItem(KEY_STORAGE);
      return {
        success: false,
        error: { name: "Login failed", message: "The gateway rejected this key." },
      };
    }
  },
  logout: async () => {
    localStorage.removeItem(KEY_STORAGE);
    return { success: true, redirectTo: "/admin/login" };
  },
  check: async () => {
    // dev mode (auth disabled on the gateway) is allowed through
    try {
      const h = await (await fetch(`${API_URL}/api/health`)).json();
      if (h.auth === "disabled") return { authenticated: true };
    } catch {
      /* gateway offline: fall through to key check */
    }
    return getKey()
      ? { authenticated: true }
      : { authenticated: false, redirectTo: "/admin/login" };
  },
  onError: async (error) => {
    if (error?.statusCode === 401)
      return { logout: true, redirectTo: "/admin/login", error };
    return { error };
  },
};
