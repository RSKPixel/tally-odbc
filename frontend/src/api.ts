export type Me = { username: string; name: string };
export type AppSettings = { tally_host: string; tally_port: number };
export type TallyStatus = {
  online: boolean;
  company: string;
  companies: string[];
  from_date: string;
  to_date: string;
  url: string;
  error: string;
};
export type CollectionInfo = { id: string; label: string };
export type FetchResult = {
  id: string;
  label: string;
  count: number;
  elapsed: string;
  columns: string[];
  rows: Record<string, string>[];
  error: string;
};
export type FetchResponse = {
  from_date: string;
  to_date: string;
  results: FetchResult[];
};
export type VoucherItems = {
  master_id: string;
  columns: string[];
  items: Record<string, string>[];
  error?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch {
    throw new Error("API not reachable. Try again.");
  }
  if (response.status === 401) {
    throw new Error("unauthorized");
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<Me>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<Me>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  settings: () => request<AppSettings>("/api/settings"),
  saveSettings: (body: AppSettings) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  profile: () => request<Me>("/api/profile"),
  saveProfile: (body: Me & { password: string }) =>
    request<Me>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  tallyStatus: () => request<TallyStatus>("/api/tally/status"),
  collections: () => request<CollectionInfo[]>("/api/tally/collections"),
  fetchCollections: (body: { collections: string[]; from_date: string; to_date: string }) =>
    request<FetchResponse>("/api/tally/fetch", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  voucherItems: (collection: string, master_id: string) =>
    request<VoucherItems>("/api/tally/voucher", {
      method: "POST",
      body: JSON.stringify({ collection, master_id }),
    }),
  mysqlDatabases: () => request<{ databases: string[] }>("/api/mysql/databases"),
  mysqlBinding: () => request<{ company: string; database: string }>("/api/mysql/binding"),
  saveMysqlBinding: (body: { database: string; password: string }) =>
    request<{ company: string; database: string }>("/api/mysql/binding", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  syncCollections: (body: { collections: string[]; from_date: string; to_date: string }) =>
    request<{
      database: string;
      results: { id: string; label: string; count: number; elapsed: string; error: string }[];
    }>("/api/tally/sync", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
