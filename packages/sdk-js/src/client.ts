import {
  SseTransport,
  WebSocketTransport,
  WebTransportCandidate,
  type RealtimeTransport,
} from "./transports.js";
import type {
  AckEvent,
  CapabilitiesResponse,
  ClientOptions,
  ConnectOptions,
  ConnectResult,
  ErrorEvent,
  ListNotificationsOptions,
  MarkAllNotificationsReadResult,
  Notification,
  PresenceStatus,
  RealtimeCommand,
  RealtimeEvent,
  RequestOptions,
  SendMessageOptions,
  SkippedTransport,
  SubscribeRoomOptions,
  TypingStatus,
  TransportName,
  UnreadNotificationCount,
} from "./types.js";

const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;

interface PendingRequest {
  resolve: (event: AckEvent) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
}

export class OpenChatRelayClient {
  private transport: RealtimeTransport | null = null;
  private readonly eventHandlers = new Set<(event: RealtimeEvent) => void>();
  private readonly pendingRequests = new Map<string, PendingRequest>();
  private readonly requestTimeoutMs: number;
  private readonly requestIdFactory: () => string;
  private readonly webTransportOptions: WebTransportOptions | undefined;

  constructor(
    private readonly baseUrl: string | URL,
    options: ClientOptions = {},
  ) {
    this.requestTimeoutMs = options.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    this.requestIdFactory = options.requestIdFactory ?? createRequestId;
    this.webTransportOptions = options.webTransportOptions;
  }

  async capabilities(): Promise<CapabilitiesResponse> {
    return this.httpJson<CapabilitiesResponse>("/v1/capabilities");
  }

  async listNotifications(options: ListNotificationsOptions): Promise<Notification[]> {
    const url = new URL("/v1/notifications", this.baseUrl);
    if (options.limit !== undefined) {
      url.searchParams.set("limit", String(options.limit));
    }
    if (options.unreadOnly !== undefined) {
      url.searchParams.set("unread_only", String(options.unreadOnly));
    }
    return this.httpJson<Notification[]>(url, { token: options.token });
  }

  async markNotificationRead(token: string, notificationId: string): Promise<Notification> {
    return this.httpJson<Notification>(`/v1/notifications/${notificationId}/read`, {
      method: "POST",
      token,
    });
  }

  async unreadNotificationCount(token: string): Promise<UnreadNotificationCount> {
    return this.httpJson<UnreadNotificationCount>("/v1/notifications/unread-count", { token });
  }

  async markAllNotificationsRead(token: string): Promise<MarkAllNotificationsReadResult> {
    return this.httpJson<MarkAllNotificationsReadResult>("/v1/notifications/read-all", {
      method: "POST",
      token,
    });
  }

  async connect(options: ConnectOptions): Promise<ConnectResult> {
    const capabilities = await this.capabilities();
    const attempted: string[] = [];
    const skipped: SkippedTransport[] = [];

    for (const transportName of capabilities.transport_negotiation.preferred_order) {
      const transportCapability = capabilities.transports[transportName];
      if (transportCapability === undefined) {
        skipped.push({
          transport: transportName,
          reason: "Transport is missing from server capabilities.",
        });
        continue;
      }
      if (!transportCapability.available) {
        skipped.push({
          transport: transportName,
          status: transportCapability.status,
          reason: transportCapability.unavailable_reason ?? "Transport is not available.",
        });
        continue;
      }
      if (transportCapability.url === null) {
        skipped.push({
          transport: transportName,
          status: transportCapability.status,
          reason: "Transport URL is not configured.",
        });
        continue;
      }

      attempted.push(transportName);
      const candidate = this.createTransport(transportName, transportCapability.url, options);
      if (candidate === null) {
        skipped.push({
          transport: transportName,
          status: transportCapability.status,
          reason: "Transport is not supported by this SDK.",
        });
        continue;
      }

      try {
        candidate.onEvent((event) => this.handleTransportEvent(event));
        await candidate.connect();
        this.transport = candidate;
        return { transport: candidate.name, attempted, skipped };
      } catch (error) {
        skipped.push({
          transport: transportName,
          status: transportCapability.status,
          reason: error instanceof Error ? error.message : "Transport connection failed.",
        });
        candidate.close();
      }
    }

    throw new RealtimeConnectError(attempted, skipped);
  }

  send(command: RealtimeCommand): void {
    if (this.transport === null) {
      throw new Error("Client is not connected.");
    }
    this.transport.send(command);
  }

  request(command: Omit<RealtimeCommand, "request_id">, options: RequestOptions = {}): Promise<AckEvent> {
    const requestId = options.requestId ?? this.requestIdFactory();
    const timeoutMs = options.timeoutMs ?? this.requestTimeoutMs;
    const commandWithRequestId: RealtimeCommand = {
      ...command,
      request_id: requestId,
    };

    const response = new Promise<AckEvent>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(requestId);
        reject(new Error(`Realtime request timed out after ${timeoutMs}ms.`));
      }, timeoutMs);
      this.pendingRequests.set(requestId, { resolve, reject, timeout });
    });

    try {
      this.send(commandWithRequestId);
    } catch (error) {
      const pending = this.pendingRequests.get(requestId);
      if (pending !== undefined) {
        clearTimeout(pending.timeout);
        this.pendingRequests.delete(requestId);
      }
      throw error;
    }

    return response;
  }

  subscribeRoom(roomId: string, options: SubscribeRoomOptions = {}): Promise<AckEvent> {
    return this.request(
      {
        type: "room.subscribe",
        data: {
          room_id: roomId,
          ...(options.lastEventSeq === undefined ? {} : { last_event_seq: options.lastEventSeq }),
        },
      },
      options,
    );
  }

  unsubscribeRoom(roomId: string, options: RequestOptions = {}): Promise<AckEvent> {
    return this.request(
      {
        type: "room.unsubscribe",
        data: { room_id: roomId },
      },
      options,
    );
  }

  sendMessage(
    roomId: string,
    content: string,
    options: SendMessageOptions = {},
  ): Promise<AckEvent> {
    return this.request(
      {
        type: "message.send",
        data: {
          room_id: roomId,
          content,
          ...(options.replyToId === undefined ? {} : { reply_to_id: options.replyToId }),
        },
      },
      options,
    );
  }

  updatePresence(
    roomId: string,
    status: PresenceStatus,
    options: RequestOptions = {},
  ): Promise<AckEvent> {
    return this.request(
      {
        type: "presence.update",
        data: { room_id: roomId, status },
      },
      options,
    );
  }

  updateTyping(
    roomId: string,
    status: TypingStatus,
    options: RequestOptions = {},
  ): Promise<AckEvent> {
    return this.request(
      {
        type: "typing.update",
        data: { room_id: roomId, status },
      },
      options,
    );
  }

  close(): void {
    this.transport?.close();
    this.transport = null;
    for (const [requestId, pending] of this.pendingRequests) {
      clearTimeout(pending.timeout);
      pending.reject(new Error("Client connection closed before the request completed."));
      this.pendingRequests.delete(requestId);
    }
  }

  onEvent(handler: (event: RealtimeEvent) => void): () => void {
    this.eventHandlers.add(handler);
    return () => {
      this.eventHandlers.delete(handler);
    };
  }

  private createTransport(
    transportName: TransportName,
    rawUrl: string,
    options: ConnectOptions,
  ): RealtimeTransport | null {
    const url = new URL(rawUrl, this.baseUrl);
    url.searchParams.set("token", options.token);
    if (options.lastEventSeq !== undefined) {
      url.searchParams.set("last_event_seq", String(options.lastEventSeq));
    }

    if (transportName === "webtransport") {
      return new WebTransportCandidate(httpUrlToWebTransportUrl(url), this.webTransportOptions);
    }
    if (transportName === "websocket") {
      return new WebSocketTransport(httpUrlToWebSocketUrl(url));
    }
    if (transportName === "sse") {
      return new SseTransport(url.toString());
    }
    return null;
  }

  private async httpJson<ResponseBody>(
    rawUrl: string | URL,
    options: RequestInit & { token?: string } = {},
  ): Promise<ResponseBody> {
    const headers = new Headers(options.headers);
    if (options.token !== undefined) {
      headers.set("Authorization", `Bearer ${options.token}`);
    }
    const response = await fetch(new URL(rawUrl, this.baseUrl), {
      ...options,
      headers,
    });
    if (!response.ok) {
      throw new Error(`HTTP request failed with ${response.status}.`);
    }
    return (await response.json()) as ResponseBody;
  }

  private handleTransportEvent(event: RealtimeEvent): void {
    this.settlePendingRequest(event);
    for (const handler of this.eventHandlers) {
      handler(event);
    }
  }

  private settlePendingRequest(event: RealtimeEvent): void {
    if (!isAckEvent(event) && !isErrorEvent(event)) {
      return;
    }
    if (event.request_id === null) {
      return;
    }

    const pending = this.pendingRequests.get(event.request_id);
    if (pending === undefined) {
      return;
    }

    clearTimeout(pending.timeout);
    this.pendingRequests.delete(event.request_id);

    if (isAckEvent(event)) {
      pending.resolve(event);
      return;
    }

    pending.reject(new RealtimeRequestError(event.code, event.message, event.request_id));
  }
}

function httpUrlToWebSocketUrl(url: URL): string {
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

function httpUrlToWebTransportUrl(url: URL): string {
  url.protocol = url.protocol === "https:" ? "https:" : "http:";
  return url.toString();
}

function createRequestId(): string {
  if (globalThis.crypto?.randomUUID !== undefined) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function isAckEvent(event: RealtimeEvent): event is AckEvent {
  return event.type === "ack";
}

function isErrorEvent(event: RealtimeEvent): event is ErrorEvent {
  return event.type === "error";
}

export class RealtimeRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId: string,
  ) {
    super(message);
    this.name = "RealtimeRequestError";
  }
}

export class RealtimeConnectError extends Error {
  constructor(
    readonly attempted: string[],
    readonly skipped: SkippedTransport[],
  ) {
    super(
      `No realtime transport could connect. Attempted: ${attempted.join(", ") || "none"}.`,
    );
    this.name = "RealtimeConnectError";
  }
}
