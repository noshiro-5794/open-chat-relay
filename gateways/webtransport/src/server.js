import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { Readable, Writable } from "node:stream";

const SERVICE_NAME = "openchatrelay-webtransport-gateway";
const DEFAULT_SESSION_TTL_SECONDS = 3600;
const DEFAULT_MAX_FRAME_BYTES = 1_048_576;
const DEFAULT_GATEWAY_INTERNAL_TOKEN = "change-this-local-gateway-token";
const DEFAULT_WEBTRANSPORT_SECRET = "change-this-local-webtransport-secret";
const FRAME_PROTOCOL = Object.freeze({
  version: "ocr.realtime.frame.v1",
  encoding: "jsonl",
  content_type: "application/x-ndjson",
  delimiter: "\n",
});
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

export function readConfig(env = process.env) {
  return {
    environment: env.OPEN_CHAT_RELAY_ENVIRONMENT ?? "local",
    host: env.OPEN_CHAT_RELAY_GATEWAY_BIND_HOST ?? "0.0.0.0",
    port: Number.parseInt(env.OPEN_CHAT_RELAY_GATEWAY_PORT ?? "8080", 10),
    apiBaseUrl: env.OPEN_CHAT_RELAY_API_BASE_URL ?? "http://api:8000",
    gatewayInternalToken: env.OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN ?? null,
    sessionTtlSeconds: Number.parseInt(
      env.OPEN_CHAT_RELAY_GATEWAY_SESSION_TTL_SECONDS ?? String(DEFAULT_SESSION_TTL_SECONDS),
      10,
    ),
    maxFrameBytes: Number.parseInt(
      env.OPEN_CHAT_RELAY_GATEWAY_MAX_FRAME_BYTES ?? String(DEFAULT_MAX_FRAME_BYTES),
      10,
    ),
    webtransportRuntimeEnabled:
      env.OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED === "true",
    webtransportCertPath: optionalEnv(env.OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_CERT_PATH),
    webtransportKeyPath: optionalEnv(env.OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_KEY_PATH),
    webtransportSecret:
      env.OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_SECRET ?? DEFAULT_WEBTRANSPORT_SECRET,
  };
}

function optionalEnv(value) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function createGatewayServer(config = readConfig(), sessions = null) {
  const gatewaySessions = sessions ?? new GatewaySessionRegistry({
    ttlSeconds: config.sessionTtlSeconds ?? DEFAULT_SESSION_TTL_SECONDS,
  });

  return createServer(async (request, response) => {
    const url = new URL(request.url ?? "/", "http://localhost");

    if (request.method === "GET" && url.pathname === "/health") {
      gatewaySessions.pruneExpired();
      writeJson(response, 200, {
        status: "ok",
        service: SERVICE_NAME,
        webtransport_runtime: config.webtransportRuntimeEnabled ? "enabled" : "pending",
        frame_protocol: frameProtocol(config),
        active_sessions: gatewaySessions.size,
      });
      return;
    }

    if (request.method === "GET" && url.pathname === "/ready") {
      await handleReady(response, config);
      return;
    }

    if (request.method === "GET" && url.pathname === "/v1/wt") {
      writeJson(response, 501, {
        detail: "This HTTP control-plane endpoint does not accept WebTransport sessions. Use HTTP/3 on the same path when the runtime is enabled.",
        service: SERVICE_NAME,
        fallback: "websocket",
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/internal/sessions") {
      await handleCreateGatewaySession(request, response, config, gatewaySessions);
      return;
    }

    const sessionCommandMatch = url.pathname.match(/^\/internal\/sessions\/([^/]+)\/commands$/);
    if (request.method === "POST" && sessionCommandMatch !== null) {
      await handleGatewaySessionCommand(
        request,
        response,
        config,
        gatewaySessions,
        sessionCommandMatch[1],
      );
      return;
    }

    const sessionStreamMatch = url.pathname.match(/^\/internal\/sessions\/([^/]+)\/streams$/);
    if (request.method === "POST" && sessionStreamMatch !== null) {
      await handleGatewaySessionStream(
        request,
        response,
        config,
        gatewaySessions,
        sessionStreamMatch[1],
      );
      return;
    }

    const sessionMatch = url.pathname.match(/^\/internal\/sessions\/([^/]+)$/);
    if (request.method === "DELETE" && sessionMatch !== null) {
      gatewaySessions.delete(sessionMatch[1]);
      writeNoContent(response);
      return;
    }

    if (request.method === "POST" && url.pathname === "/internal/authenticate") {
      await handleGatewayAuthenticate(request, response, config);
      return;
    }

    if (request.method === "POST" && url.pathname === "/internal/commands") {
      await handleGatewayCommand(request, response, config);
      return;
    }

    writeJson(response, 404, { detail: "Not found." });
  });
}

async function handleReady(response, config) {
  if (config.gatewayInternalToken === null || config.gatewayInternalToken.length === 0) {
    writeJson(response, 503, {
      status: "not_ready",
      service: SERVICE_NAME,
      detail: "OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN is not configured.",
    });
    return;
  }

  try {
    const apiReady = await fetch(new URL("/ready", config.apiBaseUrl));
    if (!apiReady.ok) {
      writeJson(response, 503, {
        status: "not_ready",
        service: SERVICE_NAME,
        api_status: apiReady.status,
      });
      return;
    }
  } catch (error) {
    writeJson(response, 503, {
      status: "not_ready",
      service: SERVICE_NAME,
      detail: `API readiness check failed: ${error.message}`,
    });
    return;
  }

  writeJson(response, 200, {
    status: "ready",
    service: SERVICE_NAME,
    webtransport_runtime: config.webtransportRuntimeEnabled ? "enabled" : "pending",
    frame_protocol: frameProtocol(config),
  });
}

async function handleGatewayAuthenticate(request, response, config) {
  let payload;
  try {
    payload = await readJson(request);
  } catch {
    writeJson(response, 400, { detail: "Invalid JSON body." });
    return;
  }

  if (typeof payload.access_token !== "string" || payload.access_token.length === 0) {
    writeJson(response, 422, { detail: "access_token is required." });
    return;
  }

  try {
    const result = await authenticateAccessToken({
      accessToken: payload.access_token,
      apiBaseUrl: config.apiBaseUrl,
      gatewayInternalToken: config.gatewayInternalToken,
    });
    writeJson(response, 200, result);
  } catch (error) {
    writeJson(response, error.statusCode ?? 502, {
      detail: error.message,
    });
  }
}

async function handleCreateGatewaySession(request, response, config, sessions) {
  let payload;
  try {
    payload = await readJson(request);
  } catch {
    writeJson(response, 400, { detail: "Invalid JSON body." });
    return;
  }

  if (typeof payload.access_token !== "string" || payload.access_token.length === 0) {
    writeJson(response, 422, { detail: "access_token is required." });
    return;
  }

  try {
    const authentication = await authenticateAccessToken({
      accessToken: payload.access_token,
      apiBaseUrl: config.apiBaseUrl,
      gatewayInternalToken: config.gatewayInternalToken,
    });
    const session = sessions.create({
      accessToken: payload.access_token,
      userId: authentication.user_id,
      tokenExpiresAt: authentication.token_expires_at,
    });
    writeJson(response, 201, {
      session_id: session.id,
      user_id: session.userId,
      token_expires_at: session.tokenExpiresAt,
      expires_at: session.expiresAt,
    });
  } catch (error) {
    writeJson(response, error.statusCode ?? 502, {
      detail: error.message,
    });
  }
}

async function handleGatewayCommand(request, response, config) {
  let payload;
  try {
    payload = await readJson(request);
  } catch {
    writeJson(response, 400, { detail: "Invalid JSON body." });
    return;
  }

  if (typeof payload.access_token !== "string" || payload.access_token.length === 0) {
    writeJson(response, 422, { detail: "access_token is required." });
    return;
  }
  if (typeof payload.command !== "object" || payload.command === null) {
    writeJson(response, 422, { detail: "command is required." });
    return;
  }

  try {
    const result = await relayCommand({
      accessToken: payload.access_token,
      command: payload.command,
      apiBaseUrl: config.apiBaseUrl,
      gatewayInternalToken: config.gatewayInternalToken,
    });
    writeJson(response, 200, result);
  } catch (error) {
    writeJson(response, error.statusCode ?? 502, {
      detail: error.message,
    });
  }
}

async function handleGatewaySessionCommand(request, response, config, sessions, sessionId) {
  const session = sessions.get(sessionId);
  if (session === null) {
    writeJson(response, 404, { detail: "Gateway session not found or expired." });
    return;
  }

  let payload;
  try {
    payload = await readJson(request);
  } catch {
    writeJson(response, 400, { detail: "Invalid JSON body." });
    return;
  }

  if (typeof payload.command !== "object" || payload.command === null) {
    writeJson(response, 422, { detail: "command is required." });
    return;
  }

  try {
    const result = await relayCommand({
      accessToken: session.accessToken,
      command: payload.command,
      apiBaseUrl: config.apiBaseUrl,
      gatewayInternalToken: config.gatewayInternalToken,
    });
    writeJson(response, 200, result);
  } catch (error) {
    writeJson(response, error.statusCode ?? 502, {
      detail: error.message,
    });
  }
}

async function handleGatewaySessionStream(request, response, config, sessions, sessionId) {
  response.writeHead(200, {
    "Content-Type": "application/x-ndjson",
  });
  await handleGatewayCommandStream({
    sessionId,
    readable: Readable.toWeb(request),
    writable: Writable.toWeb(response),
    sessions,
    apiBaseUrl: config.apiBaseUrl,
    gatewayInternalToken: config.gatewayInternalToken,
    maxFrameBytes: config.maxFrameBytes,
  });
}

export async function handleGatewayCommandStream({
  sessionId,
  readable,
  writable,
  sessions,
  apiBaseUrl,
  gatewayInternalToken,
  maxFrameBytes = DEFAULT_MAX_FRAME_BYTES,
}) {
  const writer = writable.getWriter();
  const session = sessions.get(sessionId);
  if (session === null) {
    await writeGatewayFrame(writer, {
      type: "error",
      request_id: null,
      code: "gateway_session_not_found",
      message: "Gateway session not found or expired.",
    });
    await writer.close();
    return;
  }

  const reader = readable.getReader();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += textDecoder.decode(value, { stream: true });
      if (encodedFrameLength(buffer) > maxFrameBytes && !buffer.includes("\n")) {
        await writeGatewayFrame(writer, frameTooLargeError(maxFrameBytes));
        return;
      }
      buffer = await handleCompleteCommandLines({
        buffer,
        writer,
        session,
        apiBaseUrl,
        gatewayInternalToken,
        maxFrameBytes,
      });
    }
    buffer += textDecoder.decode();
    await handleCompleteCommandLines({
      buffer: `${buffer}\n`,
      writer,
      session,
      apiBaseUrl,
      gatewayInternalToken,
      maxFrameBytes,
    });
  } finally {
    reader.releaseLock();
    await writer.close();
  }
}

async function handleCompleteCommandLines({
  buffer,
  writer,
  session,
  apiBaseUrl,
  gatewayInternalToken,
  maxFrameBytes,
}) {
  const lines = buffer.split("\n");
  const remainder = lines.pop() ?? "";
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      continue;
    }
    if (encodedFrameLength(trimmed) > maxFrameBytes) {
      await writeGatewayFrame(writer, frameTooLargeError(maxFrameBytes));
      continue;
    }
    await handleCommandLine({
      line: trimmed,
      writer,
      session,
      apiBaseUrl,
      gatewayInternalToken,
    });
  }
  return remainder;
}

async function handleCommandLine({ line, writer, session, apiBaseUrl, gatewayInternalToken }) {
  let command;
  try {
    command = JSON.parse(line);
    if (typeof command !== "object" || command === null) {
      throw new Error("Command frame must be a JSON object.");
    }
  } catch (error) {
    await writeGatewayFrame(writer, {
      type: "error",
      request_id: null,
      code: "invalid_frame",
      message: error instanceof Error ? error.message : "Invalid command frame.",
    });
    return;
  }

  try {
    const result = await relayCommand({
      accessToken: session.accessToken,
      command,
      apiBaseUrl,
      gatewayInternalToken,
    });
    await writeGatewayFrames(writer, result.frames ?? []);
  } catch (error) {
    await writeGatewayFrame(writer, {
      type: "error",
      request_id: command.request_id ?? null,
      code: "gateway_relay_failed",
      message: error instanceof Error ? error.message : "Gateway command relay failed.",
    });
  }
}

export async function startWebTransportRuntime({ config, sessions }) {
  if (!config.webtransportRuntimeEnabled) {
    return null;
  }
  if (config.webtransportCertPath == null || config.webtransportKeyPath == null) {
    throw new Error(
      "WebTransport runtime requires OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_CERT_PATH and OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_KEY_PATH.",
    );
  }

  const [{ Http3Server, quicheLoaded }, cert, privKey] = await Promise.all([
    import("@fails-components/webtransport"),
    readTextFile(config.webtransportCertPath),
    readTextFile(config.webtransportKeyPath),
  ]);
  await quicheLoaded;

  const server = new Http3Server({
    port: config.port,
    host: config.host,
    secret: config.webtransportSecret,
    cert,
    privKey,
  });
  server.setRequestCallback(async ({ header }) => {
    const rawPath = header?.[":path"] ?? "";
    const normalizedPath = normalizeWebTransportPath(rawPath);
    if (normalizedPath !== "/v1/wt") {
      return { status: 404, path: normalizedPath };
    }
    return { status: 200, path: normalizedPath };
  });
  void acceptWebTransportSessions({ server, config, sessions });
  server.startServer();
  return server;
}

export function validateGatewayStartupSettings(config) {
  if (config.environment !== "production") {
    return;
  }

  const errors = [];
  if (
    config.gatewayInternalToken === null ||
    config.gatewayInternalToken === DEFAULT_GATEWAY_INTERNAL_TOKEN ||
    isPlaceholderSecret(config.gatewayInternalToken)
  ) {
    errors.push("OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN must be changed in production.");
  }
  if (config.webtransportRuntimeEnabled) {
    if (config.webtransportCertPath === null || config.webtransportKeyPath === null) {
      errors.push(
        "OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_CERT_PATH and OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_KEY_PATH are required when the runtime is enabled.",
      );
    }
    if (
      config.webtransportSecret === DEFAULT_WEBTRANSPORT_SECRET ||
      isPlaceholderSecret(config.webtransportSecret)
    ) {
      errors.push(
        "OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_SECRET must be changed in production.",
      );
    }
  }

  if (errors.length > 0) {
    throw new Error(`Invalid production gateway settings: ${errors.join(" ")}`);
  }
}

function isPlaceholderSecret(value) {
  return typeof value === "string" && value.startsWith("replace-with-");
}

async function acceptWebTransportSessions({ server, config, sessions }) {
  const sessionStream = await server.sessionStream("/v1/wt");
  const sessionReader = sessionStream.getReader();
  while (true) {
    const { done, value } = await sessionReader.read();
    if (done) {
      return;
    }
    void handleWebTransportSession({ session: value, config, sessions });
  }
}

async function handleWebTransportSession({ session, config, sessions }) {
  let gatewaySession = null;
  try {
    await session.ready;
    const accessToken = accessTokenFromWebTransportSession(session);
    if (accessToken === null) {
      closeWebTransportSession(session, "Missing access token.");
      return;
    }

    const authentication = await authenticateAccessToken({
      accessToken,
      apiBaseUrl: config.apiBaseUrl,
      gatewayInternalToken: config.gatewayInternalToken,
    });
    gatewaySession = sessions.create({
      accessToken,
      userId: authentication.user_id,
      tokenExpiresAt: authentication.token_expires_at,
    });

    const streamReader = session.incomingBidirectionalStreams.getReader();
    while (true) {
      const { done, value } = await streamReader.read();
      if (done) {
        return;
      }
      void handleGatewayCommandStream({
        sessionId: gatewaySession.id,
        readable: value.readable,
        writable: value.writable,
        sessions,
        apiBaseUrl: config.apiBaseUrl,
        gatewayInternalToken: config.gatewayInternalToken,
        maxFrameBytes: config.maxFrameBytes,
      });
    }
  } catch {
    closeWebTransportSession(session, "WebTransport gateway session failed.");
  } finally {
    if (gatewaySession !== null) {
      sessions.delete(gatewaySession.id);
    }
  }
}

export async function authenticateAccessToken({
  accessToken,
  apiBaseUrl,
  gatewayInternalToken,
}) {
  if (gatewayInternalToken === null || gatewayInternalToken.length === 0) {
    throw new GatewayError(503, "Gateway internal token is not configured.");
  }

  const response = await fetch(new URL("/v1/internal/gateway/authenticate", apiBaseUrl), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-OpenChatRelay-Gateway-Token": gatewayInternalToken,
    },
    body: JSON.stringify({ access_token: accessToken }),
  });

  const body = await safeReadJson(response);
  if (!response.ok) {
    throw new GatewayError(response.status, body.detail ?? "Gateway authentication failed.");
  }
  return body;
}

export async function relayCommand({
  accessToken,
  command,
  apiBaseUrl,
  gatewayInternalToken,
}) {
  if (gatewayInternalToken === null || gatewayInternalToken.length === 0) {
    throw new GatewayError(503, "Gateway internal token is not configured.");
  }

  const response = await fetch(new URL("/v1/internal/gateway/commands", apiBaseUrl), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-OpenChatRelay-Gateway-Token": gatewayInternalToken,
    },
    body: JSON.stringify({ access_token: accessToken, command }),
  });

  const body = await safeReadJson(response);
  if (!response.ok) {
    throw new GatewayError(response.status, body.detail ?? "Gateway command relay failed.");
  }
  return body;
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function safeReadJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function writeJson(response, statusCode, body) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
  });
  response.end(JSON.stringify(body));
}

function writeNoContent(response) {
  response.writeHead(204);
  response.end();
}

async function writeGatewayFrames(writer, frames) {
  for (const frame of frames) {
    await writeGatewayFrame(writer, frame);
  }
}

async function writeGatewayFrame(writer, frame) {
  await writer.write(textEncoder.encode(`${JSON.stringify(frame)}\n`));
}

function frameProtocol(config) {
  return {
    ...FRAME_PROTOCOL,
    max_frame_bytes: config.maxFrameBytes ?? DEFAULT_MAX_FRAME_BYTES,
  };
}

function encodedFrameLength(frame) {
  return textEncoder.encode(frame).byteLength;
}

function frameTooLargeError(maxFrameBytes) {
  return {
    type: "error",
    request_id: null,
    code: "frame_too_large",
    message: `Command frame exceeds ${maxFrameBytes} bytes.`,
  };
}

async function readTextFile(path) {
  return readFileSync(path, "utf8");
}

function accessTokenFromWebTransportSession(session) {
  const rawPath = session.header?.[":path"] ?? session.header?.path ?? "";
  try {
    const url = new URL(rawPath, "https://openchatrelay.local");
    const token = url.searchParams.get("token");
    return token && token.length > 0 ? token : null;
  } catch {
    return null;
  }
}

function normalizeWebTransportPath(rawPath) {
  try {
    return new URL(rawPath, "https://openchatrelay.local").pathname;
  } catch {
    return rawPath;
  }
}

function closeWebTransportSession(session, reason) {
  try {
    session.close?.({ closeCode: 4001, reason });
  } catch {
    return;
  }
}

export class GatewaySessionRegistry {
  constructor({ ttlSeconds, now = () => new Date() }) {
    this.ttlMilliseconds = ttlSeconds * 1000;
    this.now = now;
    this.sessions = new Map();
  }

  get size() {
    this.pruneExpired();
    return this.sessions.size;
  }

  create({ accessToken, userId, tokenExpiresAt }) {
    const now = this.now();
    const tokenExpiry = new Date(tokenExpiresAt);
    const ttlExpiry = new Date(now.getTime() + this.ttlMilliseconds);
    const expiresAt = Number.isNaN(tokenExpiry.getTime()) || tokenExpiry > ttlExpiry
      ? ttlExpiry
      : tokenExpiry;
    const session = {
      id: randomUUID(),
      accessToken,
      userId,
      tokenExpiresAt,
      expiresAt: expiresAt.toISOString(),
      createdAt: now.toISOString(),
      lastSeenAt: now.toISOString(),
    };

    this.sessions.set(session.id, session);
    return publicSession(session);
  }

  get(sessionId) {
    const session = this.sessions.get(sessionId);
    if (session === undefined) {
      return null;
    }
    if (this.isExpired(session)) {
      this.sessions.delete(sessionId);
      return null;
    }
    session.lastSeenAt = this.now().toISOString();
    return session;
  }

  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }

  pruneExpired() {
    for (const [sessionId, session] of this.sessions.entries()) {
      if (this.isExpired(session)) {
        this.sessions.delete(sessionId);
      }
    }
  }

  isExpired(session) {
    return new Date(session.expiresAt) <= this.now();
  }
}

function publicSession(session) {
  return {
    id: session.id,
    userId: session.userId,
    tokenExpiresAt: session.tokenExpiresAt,
    expiresAt: session.expiresAt,
    createdAt: session.createdAt,
    lastSeenAt: session.lastSeenAt,
  };
}

class GatewayError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.statusCode = statusCode;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const config = readConfig();
  validateGatewayStartupSettings(config);
  const sessions = new GatewaySessionRegistry({
    ttlSeconds: config.sessionTtlSeconds ?? DEFAULT_SESSION_TTL_SECONDS,
  });
  const server = createGatewayServer(config, sessions);
  server.listen(config.port, config.host, () => {
    console.log(`${SERVICE_NAME} listening on ${config.host}:${config.port}`);
  });
  startWebTransportRuntime({ config, sessions })
    .then((runtime) => {
      if (runtime !== null) {
        console.log(`${SERVICE_NAME} WebTransport runtime listening on ${config.host}:${config.port}`);
      }
    })
    .catch((error) => {
      console.error(`${SERVICE_NAME} WebTransport runtime failed:`, error);
      process.exitCode = 1;
    });
}
