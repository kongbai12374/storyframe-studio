export type Scene = {
  description: string;
  dialogue: string;
  duration: number;
  image_id: number | null;
  audio_id: number | null;
};
export type Script = {
  id: number;
  title: string;
  synopsis: string;
  style: string;
  scenes: Scene[];
  revision: number;
};
export type Asset = {
  id: number;
  name: string;
  kind: string;
  url: string;
  thumbnail_url: string;
  tags: string;
  size: number;
  metadata: Record<string, number>;
};
export type Job = {
  id: number;
  kind: string;
  status: string;
  stage: string;
  progress: number;
  error: string;
  error_code: string;
  attempts: number;
  may_charge: boolean;
  node_statuses?: Record<string, string>;
  budget_status?: { reserved_yuan: string; limit_yuan: string | null };
  remote_status?: {
    task_id?: string;
    status?: string;
    submission_state?: string;
    cancellation?: string;
  };
  result: Record<string, unknown>;
  download_url: string | null;
  logs?: { message: string; created_at: string }[];
};
export type User = {
  id: number;
  username: string;
  name: string;
  is_admin: boolean;
  quota_bytes: number;
  used_bytes: number;
  api_calls_remaining: number;
};
export type Page<T> = {
  results: T[];
  total: number;
  page: number;
  limit: number;
};
let csrf = "";
export async function getCSRF() {
  const r = await fetch("/api/csrf/", { credentials: "same-origin" });
  csrf = (await r.json()).csrfToken;
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  if (method !== "GET") await getCSRF();
  const form = body instanceof FormData;
  const response = await fetch("/api/" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(form ? {} : { "Content-Type": "application/json" }),
      ...(method === "GET" ? {} : { "X-CSRFToken": csrf }),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  });
  if (
    response.status === 401 ||
    (response.status === 403 &&
      location.pathname !== "/login" &&
      (await response.clone().text()).includes("身份认证"))
  ) {
    location.href = "/login";
  }
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = { detail: "服务暂时无法连接" };
    }
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Object.entries(data)
            .map(([k, v]) => k + ": " + String(v))
            .join("；"),
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function key() {
  return crypto.randomUUID();
}
export function scene(): Scene {
  return {
    description: "",
    dialogue: "",
    duration: 5,
    image_id: null,
    audio_id: null,
  };
}
export const statuses: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  cancel_requested: "正在取消",
  cancelled: "已取消",
  succeeded: "已完成",
  failed: "失败",
  interrupted: "已中断",
};
