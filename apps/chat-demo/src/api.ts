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

export interface RoomMember {
  id: string;
  room_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: string;
}

export interface RoomPresenceUser {
  user_id: string;
  status: string;
}

export interface RoomPresence {
  room_id: string;
  users: RoomPresenceUser[];
}

export interface Attachment {
  id: string;
  workspace_id: string;
  room_id: string;
  message_id: string | null;
  uploader_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  storage_key: string;
  status: string;
  created_at: string;
}

export interface AttachmentUploadIntent {
  attachment: Attachment;
  upload_url: string | null;
}

export interface AttachmentDownloadIntent {
  attachment: Attachment;
  download_url: string | null;
  expires_in_seconds: number;
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
  attachments: Attachment[];
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

export function listUsers(token: string, query = ""): Promise<User[]> {
  const normalizedQuery = query.trim();
  const url =
    normalizedQuery === ""
      ? "/v1/users?limit=100"
      : `/v1/users?q=${encodeURIComponent(normalizedQuery)}&limit=100`;
  return request<User[]>(url, { token });
}

export function updateMe(token: string, displayName: string): Promise<User> {
  return request<User>("/v1/me", {
    method: "PATCH",
    token,
    body: JSON.stringify({ display_name: displayName }),
  });
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

export function startDirectConversation(
  token: string,
  workspaceId: string,
  email: string,
): Promise<Room> {
  return request<Room>(`/v1/workspaces/${workspaceId}/rooms/direct`, {
    method: "POST",
    token,
    body: JSON.stringify({ email }),
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

export function inviteRoomMember(
  token: string,
  roomId: string,
  email: string,
): Promise<RoomMember> {
  return request<RoomMember>(`/v1/rooms/${roomId}/invites`, {
    method: "POST",
    token,
    body: JSON.stringify({ email, role: "member" }),
  });
}

export function listRoomMembers(token: string, roomId: string): Promise<RoomMember[]> {
  return request<RoomMember[]>(`/v1/rooms/${roomId}/members`, { token });
}

export function leaveRoom(token: string, roomId: string): Promise<void> {
  return request<void>(`/v1/rooms/${roomId}/leave`, {
    method: "POST",
    token,
  });
}

export function listMessages(token: string, roomId: string): Promise<Message[]> {
  return request<Message[]>(`/v1/rooms/${roomId}/messages?limit=50`, { token });
}

export function createAttachmentUploadIntent(
  token: string,
  roomId: string,
  file: File,
): Promise<AttachmentUploadIntent> {
  return request<AttachmentUploadIntent>(`/v1/rooms/${roomId}/attachments`, {
    method: "POST",
    token,
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
    }),
  });
}

export async function uploadAttachmentObject(uploadUrl: string, file: File): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Attachment upload failed with HTTP ${response.status}`);
  }
}

export function confirmAttachmentUpload(
  token: string,
  roomId: string,
  attachmentId: string,
): Promise<Attachment> {
  return request<Attachment>(`/v1/rooms/${roomId}/attachments/${attachmentId}/confirm`, {
    method: "POST",
    token,
  });
}

export function createAttachmentDownloadIntent(
  token: string,
  roomId: string,
  attachmentId: string,
): Promise<AttachmentDownloadIntent> {
  return request<AttachmentDownloadIntent>(
    `/v1/rooms/${roomId}/attachments/${attachmentId}/download`,
    { token },
  );
}

export function listRoomPresence(token: string, roomId: string): Promise<RoomPresence> {
  return request<RoomPresence>(`/v1/rooms/${roomId}/presence`, { token });
}

export function searchMessages(token: string, roomId: string, query: string): Promise<Message[]> {
  const url = `/v1/rooms/${roomId}/messages/search?q=${encodeURIComponent(query)}&limit=20`;
  return request<Message[]>(url, { token });
}

export function createMessage(
  token: string,
  roomId: string,
  content: string,
  options: { replyToId?: string | null; attachmentIds?: string[] } = {},
): Promise<Message> {
  return request<Message>(`/v1/rooms/${roomId}/messages`, {
    method: "POST",
    token,
    body: JSON.stringify({
      content,
      ...(options.attachmentIds === undefined ? {} : { attachment_ids: options.attachmentIds }),
      ...(options.replyToId === undefined || options.replyToId === null
        ? {}
        : { reply_to_id: options.replyToId }),
    }),
  });
}

export function updateMessage(
  token: string,
  roomId: string,
  messageId: string,
  content: string,
): Promise<Message> {
  return request<Message>(`/v1/rooms/${roomId}/messages/${messageId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ content }),
  });
}

export function deleteMessage(token: string, roomId: string, messageId: string): Promise<Message> {
  return request<Message>(`/v1/rooms/${roomId}/messages/${messageId}/commands`, {
    method: "POST",
    token,
    body: JSON.stringify({ type: "message.delete" }),
  });
}

export function messageFromRealtimeEvent(event: Record<string, unknown>): Message | null {
  if (
    !["message.created", "message.updated", "message.deleted"].includes(String(event.type)) ||
    typeof event.data !== "object" ||
    event.data === null
  ) {
    return null;
  }
  const data = event.data as Record<string, unknown>;
  if (
    typeof data.message_id !== "string" ||
    typeof data.room_id !== "string"
  ) {
    return null;
  }
  const eventTime =
    typeof event.created_at === "string" ? event.created_at : new Date().toISOString();
  return {
    id: data.message_id,
    workspace_id: typeof event.workspace_id === "string" ? event.workspace_id : "",
    room_id: data.room_id,
    sender_type: typeof data.sender_type === "string" ? data.sender_type : "user",
    sender_id: typeof data.sender_id === "string" ? data.sender_id : null,
    sender_bot_id: typeof data.sender_bot_id === "string" ? data.sender_bot_id : null,
    message_type: typeof data.message_type === "string" ? data.message_type : "text",
    content: typeof data.content === "string" ? data.content : "",
    reply_to_id: typeof data.reply_to_id === "string" ? data.reply_to_id : null,
    created_at: eventTime,
    updated_at: eventTime,
    deleted_at: typeof data.deleted_at === "string" ? data.deleted_at : null,
    attachments: Array.isArray(data.attachments) ? (data.attachments as Attachment[]) : [],
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

  const url = new URL(path, apiBaseUrl);
  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (requestError) {
    const method = options.method ?? "GET";
    const reason = requestError instanceof Error ? requestError.message : "Network request failed.";
    throw new ApiError(0, `${method} ${url.toString()} failed before receiving a response: ${reason}`);
  }
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
