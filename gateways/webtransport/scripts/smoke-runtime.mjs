#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { X509Certificate } from "node:crypto";

import { WebTransport, quicheLoaded } from "@fails-components/webtransport";

import { GatewaySessionRegistry, startWebTransportRuntime } from "../src/server.js";

const API_BASE_URL = (
  process.env.OPEN_CHAT_RELAY_RUNTIME_SMOKE_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const GATEWAY_INTERNAL_TOKEN =
  process.env.OPEN_CHAT_RELAY_GATEWAY_INTERNAL_TOKEN ?? "change-this-local-gateway-token";
const EXTERNAL_WEBTRANSPORT_URL = process.env.OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL ?? null;
const EXTERNAL_CERT_PATH =
  process.env.OPEN_CHAT_RELAY_RUNTIME_SMOKE_CERT_PATH ?? "../../local/certs/webtransport.crt";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

async function main() {
  await quicheLoaded;
  const certificate =
    EXTERNAL_WEBTRANSPORT_URL === null
      ? createTemporaryCertificate()
      : { certPath: EXTERNAL_CERT_PATH, directory: null };
  const suffix = crypto.randomUUID().slice(0, 12);
  const auth = await requestJson(`${API_BASE_URL}/v1/auth/register`, {
    method: "POST",
    body: {
      email: `runtime-smoke-${suffix}@example.com`,
      password: "correct horse battery staple",
      display_name: "Runtime Smoke",
    },
  });
  const workspace = await requestJson(`${API_BASE_URL}/v1/workspaces`, {
    method: "POST",
    token: auth.access_token,
    body: { name: `Runtime Smoke ${suffix}` },
  });
  const room = await requestJson(`${API_BASE_URL}/v1/workspaces/${workspace.id}/rooms`, {
    method: "POST",
    token: auth.access_token,
    body: { name: "Runtime Room" },
  });

  let runtime = null;

  try {
    let url;
    if (EXTERNAL_WEBTRANSPORT_URL === null) {
      runtime = await startWebTransportRuntime({
        config: {
          webtransportRuntimeEnabled: true,
          webtransportCertPath: certificate.certPath,
          webtransportKeyPath: certificate.keyPath,
          webtransportSecret: "runtime-smoke-secret",
          host: "127.0.0.1",
          port: 0,
          apiBaseUrl: API_BASE_URL,
          gatewayInternalToken: GATEWAY_INTERNAL_TOKEN,
          maxFrameBytes: 1_048_576,
        },
        sessions: new GatewaySessionRegistry({ ttlSeconds: 60 }),
      });
      await delay(250);
      const address = runtime.address();
      url = `https://127.0.0.1:${address.port}/v1/wt`;
    } else {
      url = EXTERNAL_WEBTRANSPORT_URL;
    }

    url = withToken(url, auth.access_token);
    const transport = new WebTransport(url, {
      requireUnreliable: true,
      serverCertificateHashes: [certificateHash(certificate.certPath)],
    });
    await transport.ready;

    const stream = await transport.createBidirectionalStream();
    const writer = stream.writable.getWriter();
    await writer.write(
      encoder.encode(
        `${JSON.stringify({
          type: "message.send",
          request_id: "runtime-smoke-message",
          data: {
            room_id: room.id,
            content: "hello through real webtransport runtime",
          },
        })}\n`,
      ),
    );
    await writer.close();

    const frames = await readJsonLines(stream.readable);
    if (frames[0]?.type !== "ack") {
      throw new Error(`Expected ack frame, got ${JSON.stringify(frames[0])}`);
    }
    if (frames[1]?.type !== "message.created") {
      throw new Error(`Expected message.created frame, got ${JSON.stringify(frames[1])}`);
    }
    transport.close();
    console.log(`WebTransport runtime smoke passed for ${urlWithoutToken(url)}.`);
  } finally {
    runtime?.stopServer?.();
    if (certificate.directory !== null) {
      rmSync(certificate.directory, { recursive: true, force: true });
    }
  }
}

async function requestJson(url, { method, token, body }) {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token !== undefined) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${method} ${url} failed with HTTP ${response.status}: ${await response.text()}`);
  }
  return await response.json();
}

function createTemporaryCertificate() {
  const directory = mkdtempSync(join(tmpdir(), "openchatrelay-wt-"));
  const keyPath = join(directory, "webtransport.key");
  const certPath = join(directory, "webtransport.crt");
  execFileSync("openssl", ["ecparam", "-genkey", "-name", "prime256v1", "-out", keyPath]);
  execFileSync("openssl", [
    "req",
    "-x509",
    "-new",
    "-key",
    keyPath,
    "-out",
    certPath,
    "-subj",
    "/CN=127.0.0.1",
    "-addext",
    "subjectAltName=IP:127.0.0.1",
    "-days",
    "1",
  ]);
  return { directory, keyPath, certPath };
}

function certificateHash(certPath) {
  const certificate = new X509Certificate(readFileSync(certPath));
  return {
    algorithm: "sha-256",
    value: Buffer.from(certificate.fingerprint256.split(":").map((part) => Number.parseInt(part, 16))),
  };
}

function withToken(rawUrl, token) {
  const url = new URL(rawUrl);
  url.searchParams.set("token", token);
  return url.toString();
}

function urlWithoutToken(rawUrl) {
  const url = new URL(rawUrl);
  url.searchParams.delete("token");
  return url.toString();
}

async function readJsonLines(readable) {
  const reader = readable.getReader();
  let buffer = "";
  const frames = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim().length > 0) {
        frames.push(JSON.parse(line));
      }
    }
  }
  buffer += decoder.decode();
  if (buffer.trim().length > 0) {
    frames.push(JSON.parse(buffer));
  }
  return frames;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

main().catch((error) => {
  console.error(`WebTransport runtime smoke failed: ${error.message}`);
  process.exitCode = 1;
});
