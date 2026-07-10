import assert from "node:assert/strict";
import test from "node:test";

import {
  OpenChatRelayClient,
  RealtimeConnectError,
  RealtimeRequestError,
} from "../dist/index.js";

test("connect falls back to websocket and reports skipped transports", async () => {
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: false,
        status: "unhealthy",
        unavailable_reason: "Gateway readiness check failed.",
      },
      websocket: {
        available: true,
        status: "available",
        unavailable_reason: null,
      },
    }),
  });

  try {
    const client = new OpenChatRelayClient("http://localhost:8000");
    const result = await client.connect({ token: "access-token" });

    assert.equal(result.transport, "websocket");
    assert.deepEqual(result.attempted, ["websocket"]);
    assert.deepEqual(result.skipped, [
      {
        transport: "webtransport",
        status: "unhealthy",
        reason: "Gateway readiness check failed.",
      },
    ]);
    assert.match(globalThis.WebSocket.lastUrl, /^ws:\/\/localhost:8000\/v1\/ws/);
    assert.match(globalThis.WebSocket.lastUrl, /token=access-token/);
  } finally {
    restore();
  }
});

test("webtransport transport sends commands through bidirectional streams", async () => {
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: true,
        status: "available",
        unavailable_reason: null,
        url: "/v1/wt",
      },
      websocket: {
        available: true,
        status: "available",
        unavailable_reason: null,
      },
    }),
    webTransportClass: MockWebTransport,
  });

  try {
    const client = new OpenChatRelayClient("http://localhost:8000", {
      requestIdFactory: () => "sub-1",
      webTransportOptions: {
        serverCertificateHashes: [{ algorithm: "sha-256", value: new Uint8Array([1, 2, 3]) }],
      },
    });
    const result = await client.connect({ token: "access-token" });
    const ack = await client.subscribeRoom("room-id");

    assert.equal(result.transport, "webtransport");
    assert.deepEqual(result.attempted, ["webtransport"]);
    assert.match(MockWebTransport.lastUrl, /^http:\/\/localhost:8000\/v1\/wt/);
    assert.match(MockWebTransport.lastUrl, /token=access-token/);
    assert.deepEqual(MockWebTransport.lastOptions, {
      serverCertificateHashes: [{ algorithm: "sha-256", value: new Uint8Array([1, 2, 3]) }],
    });
    assert.deepEqual(MockWebTransport.lastCommand, {
      type: "room.subscribe",
      request_id: "sub-1",
      data: { room_id: "room-id" },
    });
    assert.deepEqual(ack, {
      type: "ack",
      request_id: "sub-1",
      status: "ok",
      event_id: null,
    });
  } finally {
    restore();
    MockWebTransport.reset();
  }
});

test("webtransport transport emits additional stream events", async () => {
  MockWebTransport.nextFrames = [
    { type: "ack", request_id: "sub-1", status: "ok", event_id: null },
    { type: "message.created", event_id: "event-id" },
  ];
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: true,
        status: "available",
        unavailable_reason: null,
        url: "/v1/wt",
      },
    }),
    webTransportClass: MockWebTransport,
  });

  try {
    const events = [];
    const client = new OpenChatRelayClient("http://localhost:8000", {
      requestIdFactory: () => "sub-1",
    });
    client.onEvent((event) => events.push(event));

    await client.connect({ token: "access-token" });
    await client.subscribeRoom("room-id");
    await waitForMicrotasks();

    assert.deepEqual(JSON.parse(JSON.stringify(events)), [
      { type: "ack", request_id: "sub-1", status: "ok", event_id: null },
      { type: "message.created", event_id: "event-id" },
    ]);
  } finally {
    restore();
    MockWebTransport.reset();
  }
});

test("webtransport handshake failure falls back without unhandled rejection", async () => {
  const unhandledRejections = [];
  const onUnhandledRejection = (reason) => {
    unhandledRejections.push(reason);
  };
  process.on("unhandledRejection", onUnhandledRejection);

  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: true,
        status: "available",
        unavailable_reason: null,
        url: "/v1/wt",
      },
      websocket: {
        available: true,
        status: "available",
        unavailable_reason: null,
      },
    }),
    webTransportClass: FailingWebTransport,
  });

  try {
    const client = new OpenChatRelayClient("https://localhost:8000");
    const result = await client.connect({ token: "access-token" });
    await waitForMicrotasks();

    assert.equal(result.transport, "websocket");
    assert.deepEqual(result.attempted, ["webtransport", "websocket"]);
    assert.deepEqual(result.skipped, [
      {
        transport: "webtransport",
        status: "available",
        reason: "Opening handshake failed.",
      },
    ]);
    assert.deepEqual(unhandledRejections, []);
  } finally {
    restore();
    process.off("unhandledRejection", onUnhandledRejection);
  }
});

test("webtransport pending connection times out and falls back", async () => {
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: true,
        status: "available",
        unavailable_reason: null,
        url: "/v1/wt",
      },
      websocket: {
        available: true,
        status: "available",
        unavailable_reason: null,
      },
    }),
    webTransportClass: HangingWebTransport,
  });

  try {
    const client = new OpenChatRelayClient("https://localhost:8000", {
      connectTimeoutMs: 10,
    });
    const result = await client.connect({ token: "access-token" });

    assert.equal(result.transport, "websocket");
    assert.deepEqual(result.attempted, ["webtransport", "websocket"]);
    assert.deepEqual(result.skipped, [
      {
        transport: "webtransport",
        status: "available",
        reason: "webtransport connection timed out after 10ms.",
      },
    ]);
    assert.equal(HangingWebTransport.closedByClient, true);
  } finally {
    restore();
    HangingWebTransport.reset();
  }
});

test("webtransport transport rejects requests on error frames", async () => {
  MockWebTransport.nextFrames = [
    {
      type: "error",
      request_id: "sub-1",
      code: "room_membership_required",
      message: "Join the room before subscribing.",
    },
  ];
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: true,
        status: "available",
        unavailable_reason: null,
        url: "/v1/wt",
      },
    }),
    webTransportClass: MockWebTransport,
  });

  try {
    const client = new OpenChatRelayClient("http://localhost:8000", {
      requestIdFactory: () => "sub-1",
    });

    await client.connect({ token: "access-token" });
    await assert.rejects(
      () => client.subscribeRoom("room-id"),
      (error) => {
        assert.ok(error instanceof RealtimeRequestError);
        assert.equal(error.code, "room_membership_required");
        assert.equal(error.requestId, "sub-1");
        return true;
      },
    );
  } finally {
    restore();
    MockWebTransport.reset();
  }
});

test("connect error includes attempted and skipped diagnostics", async () => {
  const restore = installRuntimeMocks({
    capabilities: capabilitiesResponse({
      webtransport: {
        available: false,
        status: "disabled",
        unavailable_reason: "WebTransport is disabled by configuration.",
      },
      websocket: {
        available: false,
        status: "unhealthy",
        unavailable_reason: "WebSocket gateway is down.",
      },
      sse: {
        available: false,
        status: "unhealthy",
        unavailable_reason: "SSE stream is down.",
      },
    }),
  });

  try {
    const client = new OpenChatRelayClient("http://localhost:8000");

    await assert.rejects(
      () => client.connect({ token: "access-token" }),
      (error) => {
        assert.ok(error instanceof RealtimeConnectError);
        assert.deepEqual(error.attempted, []);
        assert.deepEqual(error.skipped, [
          {
            transport: "webtransport",
            status: "disabled",
            reason: "WebTransport is disabled by configuration.",
          },
          {
            transport: "websocket",
            status: "unhealthy",
            reason: "WebSocket gateway is down.",
          },
          {
            transport: "sse",
            status: "unhealthy",
            reason: "SSE stream is down.",
          },
        ]);
        return true;
      },
    );
  } finally {
    restore();
  }
});

test("notification helpers call authenticated HTTP endpoints", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const parsedUrl = new URL(String(url));
    if (parsedUrl.pathname === "/v1/notifications") {
      return jsonResponse([
        {
          id: "notification-id",
          user_id: "user-id",
          workspace_id: "workspace-id",
          room_id: "room-id",
          event_id: "event-id",
          notification_type: "message.created",
          title: "New message",
          body: "hello",
          payload: {},
          read_at: null,
          created_at: "2026-07-10T00:00:00Z",
        },
      ]);
    }
    if (parsedUrl.pathname === "/v1/notifications/notification-id/read") {
      return jsonResponse({ id: "notification-id", read_at: "2026-07-10T00:00:01Z" });
    }
    if (parsedUrl.pathname === "/v1/notifications/unread-count") {
      return jsonResponse({ unread_count: 3 });
    }
    if (parsedUrl.pathname === "/v1/notifications/read-all") {
      return jsonResponse({ updated: 1 });
    }
    return jsonResponse({ detail: "not found" }, 404);
  };

  try {
    const client = new OpenChatRelayClient("http://localhost:8000");

    const notifications = await client.listNotifications({
      token: "access-token",
      limit: 10,
      unreadOnly: true,
    });
    const notification = await client.markNotificationRead("access-token", "notification-id");
    const unreadCount = await client.unreadNotificationCount("access-token");
    const readAll = await client.markAllNotificationsRead("access-token");

    assert.equal(notifications[0].id, "notification-id");
    assert.equal(notification.read_at, "2026-07-10T00:00:01Z");
    assert.deepEqual(unreadCount, { unread_count: 3 });
    assert.deepEqual(readAll, { updated: 1 });
    assert.equal(
      calls[0].url,
      "http://localhost:8000/v1/notifications?limit=10&unread_only=true",
    );
    assert.equal(calls[0].init.headers.get("Authorization"), "Bearer access-token");
    assert.equal(calls[1].init.method, "POST");
    assert.equal(calls[2].url, "http://localhost:8000/v1/notifications/unread-count");
    assert.equal(calls[3].init.method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

function installRuntimeMocks({ capabilities, webTransportClass }) {
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  const originalEventSource = globalThis.EventSource;
  const originalWebTransport = globalThis.WebTransport;

  globalThis.fetch = async () =>
    new Response(JSON.stringify(capabilities), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  class MockWebSocket {
    static OPEN = 1;
    static lastUrl = null;

    readyState = MockWebSocket.OPEN;
    onopen = null;
    onerror = null;
    onmessage = null;

    constructor(url) {
      MockWebSocket.lastUrl = url;
      queueMicrotask(() => this.onopen?.());
    }

    send() {
      return undefined;
    }

    close() {
      return undefined;
    }
  }

  globalThis.WebSocket = MockWebSocket;
  globalThis.EventSource = class MockEventSource {
    close() {
      return undefined;
    }
  };
  globalThis.WebTransport = webTransportClass;

  return () => {
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
    globalThis.EventSource = originalEventSource;
    globalThis.WebTransport = originalWebTransport;
  };
}

class MockWebTransport {
  static lastUrl = null;
  static lastOptions = null;
  static lastCommand = null;
  static nextFrames = null;

  ready = Promise.resolve();
  closed = new Promise(() => undefined);

  constructor(url, options) {
    MockWebTransport.lastUrl = url;
    MockWebTransport.lastOptions = options;
  }

  async createBidirectionalStream() {
    let readableController;
    const readable = new ReadableStream({
      start(controller) {
        readableController = controller;
      },
    });
    const writable = new WritableStream({
      write(chunk) {
        const rawCommand = new TextDecoder().decode(chunk).trim();
        MockWebTransport.lastCommand = JSON.parse(rawCommand);
      },
      close() {
        const requestId = MockWebTransport.lastCommand?.request_id ?? null;
        const frames = MockWebTransport.nextFrames ?? [
          {
              type: "ack",
              request_id: requestId,
              status: "ok",
              event_id: null,
          },
        ];
        for (const frame of frames) {
          readableController.enqueue(new TextEncoder().encode(`${JSON.stringify(frame)}\n`));
        }
        readableController.close();
      },
    });

    return { readable, writable };
  }

  close() {
    return undefined;
  }

  static reset() {
    MockWebTransport.lastUrl = null;
    MockWebTransport.lastOptions = null;
    MockWebTransport.lastCommand = null;
    MockWebTransport.nextFrames = null;
  }
}

class FailingWebTransport {
  ready = Promise.reject(new Error("Opening handshake failed."));
  closed = Promise.reject(new Error("Opening handshake failed."));

  close() {
    return undefined;
  }
}

class HangingWebTransport {
  static closedByClient = false;

  ready = new Promise(() => undefined);
  closed = new Promise(() => undefined);

  close() {
    HangingWebTransport.closedByClient = true;
  }

  static reset() {
    HangingWebTransport.closedByClient = false;
  }
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function capabilitiesResponse(overrides) {
  return {
    transports: {
      webtransport: transportCapability({
        available: false,
        status: "disabled",
        unavailable_reason: "WebTransport is disabled.",
      }),
      websocket: transportCapability({ available: true }),
      sse: transportCapability({
        available: true,
        url: "/v1/events/stream",
        priority: 30,
        mode: "server_stream",
        supports_reliable_streams: false,
        fallback_to: null,
      }),
      ...Object.fromEntries(
        Object.entries(overrides).map(([transport, value]) => [
          transport,
          transportCapability(value),
        ]),
      ),
    },
    transport_negotiation: {
      version: "ocr.transport.v1",
      preferred_order: ["webtransport", "websocket", "sse"],
      fallback_policy: "first_available",
      resume_parameter: "last_event_seq",
    },
    features: {
      durable_events: true,
      ephemeral_signals: true,
      session_resume: true,
      datagrams: false,
    },
    protocol: {
      version: "ocr.realtime.v1",
      realtime_commands: ["room.subscribe"],
      event_types: ["message.created"],
    },
    realtime_frame: {
      version: "ocr.realtime.frame.v1",
      encoding: "jsonl",
      content_type: "application/x-ndjson",
      delimiter: "\n",
      max_frame_bytes: 1_048_576,
    },
  };
}

function transportCapability(overrides) {
  return {
    available: true,
    status: "available",
    unavailable_reason: null,
    url: "/v1/ws",
    experimental: false,
    priority: 20,
    mode: "bidirectional",
    supports_reliable_streams: true,
    supports_datagrams: false,
    supports_session_resume: true,
    fallback_to: "sse",
    ...overrides,
  };
}

function waitForMicrotasks() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
