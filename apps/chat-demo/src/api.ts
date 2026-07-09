const DEFAULT_API_BASE_URL =
  window.__OPEN_CHAT_RELAY_DEMO_CONFIG__?.apiBaseUrl ??
  import.meta.env.VITE_OPEN_CHAT_RELAY_API_BASE_URL ??
  "http://localhost:8000";

let apiBaseUrl = normalizeBaseUrl(DEFAULT_API_BASE_URL);

export function getApiBaseUrl(): string {
  return apiBaseUrl;
}

export function setApiBaseUrl(value: string): void {
  apiBaseUrl = normalizeBaseUrl(value);
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  is_system_admin: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: User;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  role: string;
}

export interface Room {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  is_private: boolean;
  role: string | null;
}

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: string;
}

export interface Message {
  id: string;
  workspace_id: string;
  room_id: string;
  sender_type: string;
  sender_id: string | null;
  sender_bot_id: string | null;
  message_type: string;
  content: string;
  reply_to_id: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  attachments: unknown[];
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

export function login(email: string, password: string): Promise<TokenPair> {
  return request<TokenPair>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function register(
  email: string,
  password: string,
  displayName: string,
): Promise<TokenPair> {
  return request<TokenPair>("/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
}

export function listWorkspaces(token: string): Promise<Workspace[]> {
  return request<Workspace[]>("/v1/workspaces", { token });
}

export function createWorkspace(token: string, name: string): Promise<Workspace> {
  return request<Workspace>("/v1/workspaces", {
    method: "POST",
    token,
    body: JSON.stringify({ name }),
  });
}

export function listRooms(token: string, workspaceId: string): Promise<Room[]> {
  return request<Room[]>(`/v1/workspaces/${workspaceId}/rooms`, { token });
}

export function createRoom(
  token: string,
  workspaceId: string,
  name: string,
  options: { isPrivate?: boolean } = {},
): Promise<Room> {
  return request<Room>(`/v1/workspaces/${workspaceId}/rooms`, {
    method: "POST",
    token,
    body: JSON.stringify({ name, is_private: options.isPrivate ?? false }),
  });
}

export function listWorkspaceMembers(token: string, workspaceId: string): Promise<WorkspaceMember[]> {
  return request<WorkspaceMember[]>(`/v1/workspaces/${workspaceId}/members`, { token });
}

export function addWorkspaceMember(
  token: string,
  workspaceId: string,
  email: string,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(`/v1/workspaces/${workspaceId}/members`, {
    method: "POST",
    token,
    body: JSON.stringify({ email, role: "member" }),
  });
}

export function addRoomMember(
  token: string,
  roomId: string,
  userId: string,
): Promise<void> {
  return request<void>(`/v1/rooms/${roomId}/members`, {
    method: "POST",
    token,
    body: JSON.stringify({ user_id: userId, role: "member" }),
  });
}

export function listMessages(token: string, roomId: string): Promise<Message[]> {
  return request<Message[]>(`/v1/rooms/${roomId}/messages?limit=50`, { token });
}

export function createMessage(token: string, roomId: string, content: string): Promise<Message> {
  return request<Message>(`/v1/rooms/${roomId}/messages`, {
    method: "POST",
    token,
    body: JSON.stringify({ content }),
  });
}

export function messageFromRealtimeEvent(event: Record<string, unknown>): Message | null {
  if (event.type !== "message.created" || typeof event.data !== "object" || event.data === null) {
    return null;
  }
  const data = event.data as Record<string, unknown>;
  if (
    typeof data.message_id !== "string" ||
    typeof data.room_id !== "string" ||
    typeof data.content !== "string"
  ) {
    return null;
  }
  return {
    id: data.message_id,
    workspace_id: typeof event.workspace_id === "string" ? event.workspace_id : "",
    room_id: data.room_id,
    sender_type: typeof data.sender_type === "string" ? data.sender_type : "user",
    sender_id: typeof data.sender_id === "string" ? data.sender_id : null,
    sender_bot_id: typeof data.sender_bot_id === "string" ? data.sender_bot_id : null,
    message_type: typeof data.message_type === "string" ? data.message_type : "text",
    content: data.content,
    reply_to_id: typeof data.reply_to_id === "string" ? data.reply_to_id : null,
    created_at: typeof event.created_at === "string" ? event.created_at : new Date().toISOString(),
    updated_at: typeof event.created_at === "string" ? event.created_at : new Date().toISOString(),
    deleted_at: null,
    attachments: Array.isArray(data.attachments) ? data.attachments : [],
  };
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token !== undefined) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(new URL(path, apiBaseUrl), {
    ...options,
    headers,
  });
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      // Keep the status-based message for non-JSON responses.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}
