declare global {
  interface Window {
    __OPEN_CHAT_RELAY_CONSOLE_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

const API_BASE_URL =
  window.__OPEN_CHAT_RELAY_CONSOLE_CONFIG__?.apiBaseUrl ??
  import.meta.env.VITE_OPEN_CHAT_RELAY_API_BASE_URL ??
  "http://localhost:8000";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  is_system_admin: boolean;
}

export interface SystemUser extends User {
  created_at: string;
  updated_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: User;
}

export interface SystemStatus {
  status: "ok" | "degraded";
  service: string;
  version: string;
  environment: string;
  components: Record<
    string,
    {
      status: "ok" | "degraded" | "unavailable" | "skipped" | "disabled";
      detail: string | null;
    }
  >;
  outbox: {
    pending: number;
    failed: number;
  };
  active_auth_sessions: number;
}

export interface SystemMetrics {
  realtime: {
    active_connections: number;
    active_users: number;
    subscribed_rooms: number;
    room_subscriptions: number;
  };
  outbox: {
    pending: number;
    failed: number;
  };
  notifications: {
    total: number;
    unread: number;
  };
  active_auth_sessions: number;
}

export interface SystemConfig {
  environment: string;
  debug: boolean;
  docs_enabled: boolean;
  cors_origins: string[];
  max_request_body_bytes: number;
  rate_limit_enabled: boolean;
  rate_limit_backend: string;
  storage_backend: string;
  attachment_verification: boolean;
  presence_backend: string;
  typing_backend: string;
  redis_fanout_enabled: boolean;
  redis_signals_enabled: boolean;
  webtransport_enabled: boolean;
  webtransport_url: string | null;
  webtransport_health_url: string | null;
}

export interface Capabilities {
  transports: Record<
    string,
    {
      available: boolean;
      status: "available" | "disabled" | "unhealthy";
      unavailable_reason: string | null;
      url: string | null;
      experimental: boolean;
      priority: number;
      mode: "bidirectional" | "server_stream";
      supports_reliable_streams: boolean;
      supports_datagrams: boolean;
      supports_session_resume: boolean;
      fallback_to: string | null;
    }
  >;
  transport_negotiation: {
    version: string;
    preferred_order: string[];
    fallback_policy: "first_available" | "strict";
    resume_parameter: string;
  };
  features: Record<string, boolean>;
  protocol: {
    version: string;
    realtime_commands: string[];
    event_types: string[];
  };
  realtime_frame: {
    version: string;
    encoding: "jsonl";
    content_type: string;
    delimiter: string;
    max_frame_bytes: number;
  };
}

export interface SystemAuditLog {
  id: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function login(email: string, password: string): Promise<TokenPair> {
  return request<TokenPair>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(
  email: string,
  password: string,
  displayName: string,
): Promise<TokenPair> {
  return request<TokenPair>("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
}

export async function me(token: string): Promise<User> {
  return request<User>("/v1/me", { token });
}

export async function systemStatus(token: string): Promise<SystemStatus> {
  return request<SystemStatus>("/v1/system/status", { token });
}

export async function capabilities(token: string): Promise<Capabilities> {
  return request<Capabilities>("/v1/capabilities", { token });
}

export async function systemMetrics(token: string): Promise<SystemMetrics> {
  return request<SystemMetrics>("/v1/system/metrics", { token });
}

export async function systemConfig(token: string): Promise<SystemConfig> {
  return request<SystemConfig>("/v1/system/config", { token });
}

export async function systemUsers(token: string): Promise<SystemUser[]> {
  return request<SystemUser[]>("/v1/system/users", { token });
}

export async function updateSystemUser(
  token: string,
  userId: string,
  payload: Partial<Pick<SystemUser, "is_active" | "is_system_admin">>,
): Promise<SystemUser> {
  return request<SystemUser>(`/v1/system/users/${userId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
}

export async function systemAuditLogs(token: string): Promise<SystemAuditLog[]> {
  return request<SystemAuditLog[]>("/v1/system/audit-logs?limit=100", { token });
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (options.token !== undefined) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(new URL(path, API_BASE_URL), {
    ...options,
    headers,
  });
  if (!response.ok) {
    const message = await errorMessage(response);
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    return response.statusText;
  }
  return response.statusText;
}
