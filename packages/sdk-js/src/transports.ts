import type { RealtimeCommand, RealtimeEvent } from "./types.js";

export interface RealtimeTransport {
  readonly name: string;
  connect(): Promise<void>;
  send(command: RealtimeCommand): void;
  close(): void;
  onEvent(handler: (event: RealtimeEvent) => void): void;
}

export class WebSocketTransport implements RealtimeTransport {
  readonly name = "websocket";
  private socket: WebSocket | null = null;
  private eventHandler: ((event: RealtimeEvent) => void) | null = null;

  constructor(
    private readonly url: string,
    private readonly options?: WebTransportOptions,
  ) {}

  async connect(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(this.url);
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error("WebSocket connection failed."));
      socket.onmessage = (message) => {
        if (this.eventHandler === null) {
          return;
        }
        this.eventHandler(JSON.parse(String(message.data)) as RealtimeEvent);
      };
      this.socket = socket;
    });
  }

  send(command: RealtimeCommand): void {
    if (this.socket === null || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket is not connected.");
    }
    this.socket.send(JSON.stringify(command));
  }

  close(): void {
    this.socket?.close();
  }

  onEvent(handler: (event: RealtimeEvent) => void): void {
    this.eventHandler = handler;
  }
}

export class SseTransport implements RealtimeTransport {
  readonly name = "sse";
  private eventSource: EventSource | null = null;
  private eventHandler: ((event: RealtimeEvent) => void) | null = null;

  constructor(
    private readonly url: string,
    private readonly options?: WebTransportOptions,
  ) {}

  async connect(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const eventSource = new EventSource(this.url);
      eventSource.onopen = () => resolve();
      eventSource.onerror = () => reject(new Error("SSE connection failed."));
      eventSource.onmessage = (message) => {
        if (this.eventHandler === null) {
          return;
        }
        this.eventHandler(JSON.parse(message.data) as RealtimeEvent);
      };
      this.eventSource = eventSource;
    });
  }

  send(_command: RealtimeCommand): void {
    throw new Error("SSE transport is receive-only. Use HTTP APIs to send commands.");
  }

  close(): void {
    this.eventSource?.close();
  }

  onEvent(handler: (event: RealtimeEvent) => void): void {
    this.eventHandler = handler;
  }
}

export class WebTransportCandidate implements RealtimeTransport {
  readonly name = "webtransport";
  private transport: WebTransport | null = null;
  private eventHandler: ((event: RealtimeEvent) => void) | null = null;
  private readonly encoder = new TextEncoder();
  private readonly decoder = new TextDecoder();

  constructor(
    private readonly url: string,
    private readonly options?: WebTransportOptions,
  ) {}

  async connect(): Promise<void> {
    const webTransportConstructor = globalThis.WebTransport;
    if (typeof webTransportConstructor === "undefined") {
      throw new Error("WebTransport is not available in this runtime.");
    }

    const transport = new webTransportConstructor(this.url, this.options);
    this.transport = transport;
    const closedBeforeReady = transport.closed.then(
      () => {
        throw new Error("WebTransport closed before the connection became ready.");
      },
      (error: unknown) => {
        throw normalizeWebTransportError(error);
      },
    );
    void closedBeforeReady.catch(() => undefined);
    void transport.ready.catch(() => undefined);

    try {
      await Promise.race([transport.ready, closedBeforeReady]);
    } catch (error) {
      this.transport = null;
      transport.close();
      throw normalizeWebTransportError(error);
    }
  }

  send(command: RealtimeCommand): void {
    if (this.transport === null) {
      throw new Error("WebTransport is not connected.");
    }
    void this.sendCommandStream(this.transport, command);
  }

  close(): void {
    this.transport?.close();
    this.transport = null;
  }

  onEvent(handler: (event: RealtimeEvent) => void): void {
    this.eventHandler = handler;
  }

  private async sendCommandStream(
    transport: WebTransport,
    command: RealtimeCommand,
  ): Promise<void> {
    try {
      const stream = await transport.createBidirectionalStream();
      const writer = stream.writable.getWriter();
      await writer.write(this.encoder.encode(`${JSON.stringify(command)}\n`));
      await writer.close();
      await this.readEventStream(stream.readable);
    } catch (error) {
      this.emit({
        type: "error",
        request_id: command.request_id ?? null,
        code: "webtransport_stream_failed",
        message: error instanceof Error ? error.message : "WebTransport stream failed.",
      });
    }
  }

  private async readEventStream(readable: ReadableStream<Uint8Array>): Promise<void> {
    const reader = readable.getReader();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += this.decoder.decode(value, { stream: true });
        buffer = this.emitCompleteLines(buffer);
      }
      buffer += this.decoder.decode();
      this.emitCompleteLines(`${buffer}\n`);
    } finally {
      reader.releaseLock();
    }
  }

  private emitCompleteLines(buffer: string): string {
    const lines = buffer.split("\n");
    const remainder = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.length === 0) {
        continue;
      }
      this.emit(JSON.parse(trimmed) as RealtimeEvent);
    }
    return remainder;
  }

  private emit(event: RealtimeEvent): void {
    this.eventHandler?.(event);
  }
}

function normalizeWebTransportError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }
  return new Error("WebTransport connection failed.");
}
