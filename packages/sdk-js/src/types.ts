export type TransportName = "webtransport" | "websocket" | "sse";
export type PresenceStatus = "online" | "away" | "busy";
export type TypingStatus = "started" | "stopped";

export interface TransportCapability {
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

export interface TransportNegotiation {
  version: string;
  preferred_order: TransportName[];
  fallback_policy: "first_available" | "strict";
  resume_parameter: string;
}

export interface CapabilitiesResponse {
  transports: Record<TransportName, TransportCapability>;
  transport_negotiation: TransportNegotiation;
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

export interface RealtimeCommand {
  type: string;
  request_id?: string | null;
  data?: Record<string, unknown>;
}

export interface RealtimeEvent {
  type: string;
  [key: string]: unknown;
}

export interface AckEvent extends RealtimeEvent {
  type: "ack";
  request_id: string | null;
  status: "ok";
  event_id: string | null;
}

export interface ErrorEvent extends RealtimeEvent {
  type: "error";
  request_id: string | null;
  code: string;
  message: string;
}

export interface ConnectOptions {
  token: string;
  lastEventSeq?: number;
}

export interface SkippedTransport {
  transport: TransportName;
  reason: string;
  status?: TransportCapability["status"];
}

export interface ConnectResult {
  transport: string;
  attempted: string[];
  skipped: SkippedTransport[];
}

export interface ClientOptions {
  requestTimeoutMs?: number;
  connectTimeoutMs?: number;
  requestIdFactory?: () => string;
  webTransportOptions?: WebTransportOptions;
}

export interface RequestOptions {
  requestId?: string;
  timeoutMs?: number;
}

export interface SubscribeRoomOptions extends RequestOptions {
  lastEventSeq?: number;
}

export interface SendMessageOptions extends RequestOptions {
  replyToId?: string;
}

export interface Notification {
  id: string;
  user_id: string;
  workspace_id: string;
  room_id: string | null;
  event_id: string;
  notification_type: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface ListNotificationsOptions {
  token: string;
  limit?: number;
  unreadOnly?: boolean;
}

export interface MarkAllNotificationsReadResult {
  updated: number;
}

export interface UnreadNotificationCount {
  unread_count: number;
}
