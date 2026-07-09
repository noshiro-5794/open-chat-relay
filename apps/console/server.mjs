import { createReadStream, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const host = process.env.OPEN_CHAT_RELAY_CONSOLE_BIND_HOST ?? "0.0.0.0";
const port = Number.parseInt(process.env.OPEN_CHAT_RELAY_CONSOLE_PORT ?? "8080", 10);
const apiBaseUrl =
  process.env.OPEN_CHAT_RELAY_CONSOLE_API_BASE_URL ?? "http://localhost:8000";
const distDir = new URL("./dist/", import.meta.url).pathname;

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");

  if (request.method !== "GET" && request.method !== "HEAD") {
    write(response, 405, "Method not allowed", "text/plain; charset=utf-8");
    return;
  }

  if (url.pathname === "/health") {
    writeJson(response, 200, { status: "ok", service: "openchatrelay-console" });
    return;
  }

  if (url.pathname === "/config.js") {
    write(
      response,
      200,
      `window.__OPEN_CHAT_RELAY_CONSOLE_CONFIG__=${JSON.stringify({ apiBaseUrl })};`,
      "text/javascript; charset=utf-8",
    );
    return;
  }

  const filePath = safeFilePath(url.pathname);
  if (filePath !== null && existsSync(filePath)) {
    streamFile(response, filePath);
    return;
  }

  const indexPath = join(distDir, "index.html");
  if (existsSync(indexPath)) {
    streamFile(response, indexPath);
    return;
  }

  write(response, 404, "Not found", "text/plain; charset=utf-8");
});

server.listen(port, host, () => {
  console.log(`openchatrelay-console listening on ${host}:${port}`);
});

function safeFilePath(pathname) {
  const normalizedPath = normalize(decodeURIComponent(pathname)).replace(/^(\.\.[/\\])+/, "");
  const relativePath = normalizedPath === "/" ? "/index.html" : normalizedPath;
  const filePath = join(distDir, relativePath);
  if (!filePath.startsWith(distDir)) {
    return null;
  }
  return filePath;
}

async function streamFile(response, filePath) {
  const contentType = contentTypes[extname(filePath)] ?? "application/octet-stream";
  try {
    await readFile(filePath);
  } catch {
    write(response, 404, "Not found", "text/plain; charset=utf-8");
    return;
  }
  response.writeHead(200, { "Content-Type": contentType });
  createReadStream(filePath).pipe(response);
}

function writeJson(response, statusCode, body) {
  write(response, statusCode, JSON.stringify(body), "application/json; charset=utf-8");
}

function write(response, statusCode, body, contentType) {
  response.writeHead(statusCode, { "Content-Type": contentType });
  response.end(body);
}
