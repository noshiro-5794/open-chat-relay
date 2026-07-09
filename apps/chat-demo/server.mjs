import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const port = Number.parseInt(process.env.OPEN_CHAT_RELAY_DEMO_PORT ?? "8080", 10);
const host = process.env.OPEN_CHAT_RELAY_DEMO_BIND_HOST ?? "0.0.0.0";
const apiBaseUrl =
  process.env.OPEN_CHAT_RELAY_DEMO_API_BASE_URL ?? "http://localhost:8000";
const root = join(process.cwd(), "dist");

const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".json", "application/json; charset=utf-8"],
]);

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  if (url.pathname === "/health") {
    write(response, 200, "application/json; charset=utf-8", {
      status: "ok",
      service: "openchatrelay-chat-demo",
    });
    return;
  }
  if (url.pathname === "/config.js") {
    response.writeHead(200, { "Content-Type": "text/javascript; charset=utf-8" });
    response.end(
      `window.__OPEN_CHAT_RELAY_DEMO_CONFIG__=${JSON.stringify({ apiBaseUrl })};`,
    );
    return;
  }

  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
  const safePath = normalize(pathname).replace(/^(\.\.[/\\])+/, "");
  const filePath = join(root, safePath);
  try {
    const content = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": contentTypes.get(extname(filePath)) ?? "application/octet-stream",
      "Cache-Control": filePath.endsWith("index.html") ? "no-store" : "public, max-age=31536000",
    });
    response.end(content);
  } catch {
    const fallback = await readFile(join(root, "index.html"));
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
    });
    response.end(fallback);
  }
}).listen(port, host, () => {
  console.log(`openchatrelay-chat-demo listening on ${host}:${port}`);
});

function write(response, statusCode, contentType, body) {
  response.writeHead(statusCode, { "Content-Type": contentType });
  response.end(JSON.stringify(body));
}
