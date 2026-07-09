import {
  Activity,
  CheckCircle2,
  KeyRound,
  LogOut,
  RadioTower,
  RefreshCw,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createRoot } from "react-dom/client";

import {
  ApiError,
  Capabilities,
  SystemAuditLog,
  SystemConfig,
  SystemMetrics,
  SystemStatus,
  SystemUser,
  User,
  capabilities,
  login,
  me,
  register,
  systemAuditLogs,
  systemConfig,
  systemMetrics,
  systemStatus,
  systemUsers,
  updateSystemUser,
} from "./api";
import "./styles.css";

type View = "status" | "transport" | "config" | "users" | "audit";

interface Session {
  token: string;
  user: User;
}

const TOKEN_STORAGE_KEY = "openchatrelay.console.accessToken";

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (token === null) {
      setBooting(false);
      return;
    }
    me(token)
      .then((user) => setSession({ token, user }))
      .catch(() => localStorage.removeItem(TOKEN_STORAGE_KEY))
      .finally(() => setBooting(false));
  }, []);

  if (booting) {
    return <div className="boot">OpenChatRelay Console</div>;
  }

  if (session === null) {
    return (
      <LoginScreen
        error={error}
        onLogin={(nextSession) => {
          localStorage.setItem(TOKEN_STORAGE_KEY, nextSession.token);
          setSession(nextSession);
          setError(null);
        }}
        onError={setError}
      />
    );
  }

  return (
    <ConsoleShell
      session={session}
      onLogout={() => {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setSession(null);
      }}
    />
  );
}

function LoginScreen({
  error,
  onLogin,
  onError,
}: {
  error: string | null;
  onLogin: (session: Session) => void;
  onError: (message: string | null) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    onError(null);
    try {
      const tokenPair =
        mode === "login" ? await login(email, password) : await register(email, password, displayName);
      onLogin({ token: tokenPair.access_token, user: tokenPair.user });
    } catch (error) {
      onError(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel">
        <div>
          <p className="eyebrow">OpenChatRelay</p>
          <h1>Console</h1>
        </div>
        <div className="mode-tabs">
          <button
            className={mode === "login" ? "active" : ""}
            type="button"
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            type="button"
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>
        <form onSubmit={submit} className="login-form">
          {mode === "register" && (
            <label>
              <span>Display name</span>
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
              />
            </label>
          )}
          <label>
            <span>Email</span>
            <input
              autoComplete="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error !== null && <p className="error-text">{error}</p>}
          <button className="primary-button" type="submit" disabled={loading}>
            <KeyRound size={16} />
            {loading ? "Working" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </section>
    </main>
  );
}

function ConsoleShell({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [view, setView] = useState<View>("status");

  return (
    <main className="console-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">OpenChatRelay</p>
          <strong>Console</strong>
        </div>
        <nav className="nav-list">
          <NavButton active={view === "status"} icon={<Activity size={16} />} onClick={() => setView("status")}>
            Status
          </NavButton>
          <NavButton active={view === "transport"} icon={<RadioTower size={16} />} onClick={() => setView("transport")}>
            Transport
          </NavButton>
          <NavButton active={view === "config"} icon={<Settings size={16} />} onClick={() => setView("config")}>
            Config
          </NavButton>
          <NavButton active={view === "users"} icon={<Users size={16} />} onClick={() => setView("users")}>
            Users
          </NavButton>
          <NavButton active={view === "audit"} icon={<ShieldCheck size={16} />} onClick={() => setView("audit")}>
            Audit
          </NavButton>
        </nav>
        <div className="session-block">
          <span>{session.user.email}</span>
          <button className="icon-button" type="button" title="Sign out" onClick={onLogout}>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <section className="content">
        <header className="content-header">
          <div>
            <p className="eyebrow">System</p>
            <h2>{viewTitle(view)}</h2>
          </div>
          <StatusPill ok={session.user.is_system_admin} label="System admin" />
        </header>
        {view === "status" && <StatusView token={session.token} />}
        {view === "transport" && <TransportView token={session.token} />}
        {view === "config" && <ConfigView token={session.token} />}
        {view === "users" && <UsersView token={session.token} />}
        {view === "audit" && <AuditView token={session.token} />}
      </section>
    </main>
  );
}

function NavButton({
  active,
  icon,
  children,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className={`nav-button ${active ? "active" : ""}`} type="button" onClick={onClick}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

function StatusView({ token }: { token: string }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useMemo(
    () => async () => {
      setLoading(true);
      setError(null);
      try {
        const [nextStatus, nextMetrics] = await Promise.all([
          systemStatus(token),
          systemMetrics(token),
        ]);
        setStatus(nextStatus);
        setMetrics(nextMetrics);
      } catch (error) {
        setError(readableError(error));
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section className="panel">
      <PanelToolbar title="Runtime" onRefresh={refresh} loading={loading} />
      {error !== null && <p className="error-text">{error}</p>}
      {status !== null && (
        <>
          <div className="metric-grid">
            <Metric label="Status" value={status.status} />
            <Metric label="Environment" value={status.environment} />
            <Metric label="Auth sessions" value={String(metrics?.active_auth_sessions ?? status.active_auth_sessions)} />
            <Metric label="Connections" value={String(metrics?.realtime.active_connections ?? 0)} />
            <Metric label="Active users" value={String(metrics?.realtime.active_users ?? 0)} />
            <Metric label="Room subscriptions" value={String(metrics?.realtime.room_subscriptions ?? 0)} />
            <Metric label="Outbox pending" value={String(metrics?.outbox.pending ?? status.outbox.pending)} />
            <Metric label="Unread notifications" value={String(metrics?.notifications.unread ?? 0)} />
          </div>
          <table>
            <thead>
              <tr>
                <th>Component</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(status.components).map(([name, component]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>
                    <StatusPill ok={component.status === "ok" || component.status === "skipped"} label={component.status} />
                  </td>
                  <td>{component.detail ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function TransportView({ token }: { token: string }) {
  const [data, setData] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setData(await capabilities(token));
    } catch (error) {
      setError(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="panel">
      <PanelToolbar title="Transport negotiation" onRefresh={refresh} loading={loading} />
      {error !== null && <p className="error-text">{error}</p>}
      {data !== null && (
        <>
          <div className="metric-grid">
            <Metric label="Negotiation" value={data.transport_negotiation.version} />
            <Metric label="Policy" value={data.transport_negotiation.fallback_policy} />
            <Metric label="Resume" value={data.transport_negotiation.resume_parameter} />
            <Metric label="Protocol" value={data.protocol.version} />
            <Metric label="Frame codec" value={data.realtime_frame.encoding} />
            <Metric label="Frame version" value={data.realtime_frame.version} />
          </div>
          <table>
            <thead>
              <tr>
                <th>Transport</th>
                <th>Status</th>
                <th>Mode</th>
                <th>Datagrams</th>
                <th>Fallback</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {data.transport_negotiation.preferred_order.map((name) => {
                const transport = data.transports[name];
                if (transport === undefined) {
                  return null;
                }
                return (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>
                      <StatusPill ok={transport.available} label={transport.status} />
                    </td>
                    <td>{transport.mode}</td>
                    <td>{transport.supports_datagrams ? "yes" : "no"}</td>
                    <td>{transport.fallback_to ?? ""}</td>
                    <td>{transport.url ?? transport.unavailable_reason ?? ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function ConfigView({ token }: { token: string }) {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setConfig(await systemConfig(token));
    } catch (error) {
      setError(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const rows =
    config === null
      ? []
      : [
          ["Environment", config.environment],
          ["Debug", formatBoolean(config.debug)],
          ["Docs", formatBoolean(config.docs_enabled)],
          ["CORS origins", config.cors_origins.join(", ")],
          ["Max request body", formatBytes(config.max_request_body_bytes)],
          ["Rate limit", formatBoolean(config.rate_limit_enabled)],
          ["Rate limit backend", config.rate_limit_backend],
          ["Storage backend", config.storage_backend],
          ["Attachment verification", formatBoolean(config.attachment_verification)],
          ["Presence backend", config.presence_backend],
          ["Typing backend", config.typing_backend],
          ["Redis fanout", formatBoolean(config.redis_fanout_enabled)],
          ["Redis signals", formatBoolean(config.redis_signals_enabled)],
          ["WebTransport", formatBoolean(config.webtransport_enabled)],
          ["WebTransport URL", config.webtransport_url ?? ""],
          ["WebTransport health", config.webtransport_health_url ?? ""],
        ];

  return (
    <section className="panel">
      <PanelToolbar title="Runtime config" onRefresh={refresh} loading={loading} />
      {error !== null && <p className="error-text">{error}</p>}
      {config !== null && (
        <>
          <div className="metric-grid">
            <Metric label="Environment" value={config.environment} />
            <Metric label="Rate limit" value={config.rate_limit_backend} />
            <Metric label="Storage" value={config.storage_backend} />
            <Metric label="WebTransport" value={config.webtransport_enabled ? "enabled" : "disabled"} />
          </div>
          <table>
            <thead>
              <tr>
                <th>Setting</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, value]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function UsersView({ token }: { token: string }) {
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setUsers(await systemUsers(token));
    } catch (error) {
      setError(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  async function toggle(user: SystemUser, field: "is_active" | "is_system_admin") {
    setError(null);
    try {
      const updated = await updateSystemUser(token, user.id, { [field]: !user[field] });
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setError(readableError(error));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="panel">
      <PanelToolbar title="Users" onRefresh={refresh} loading={loading} />
      {error !== null && <p className="error-text">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Active</th>
            <th>Admin</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.email}</td>
              <td>{user.display_name}</td>
              <td>
                <button className="toggle-button" type="button" onClick={() => void toggle(user, "is_active")}>
                  {user.is_active ? "Enabled" : "Disabled"}
                </button>
              </td>
              <td>
                <button className="toggle-button" type="button" onClick={() => void toggle(user, "is_system_admin")}>
                  {user.is_system_admin ? "Admin" : "User"}
                </button>
              </td>
              <td>{formatDate(user.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AuditView({ token }: { token: string }) {
  const [logs, setLogs] = useState<SystemAuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setLogs(await systemAuditLogs(token));
    } catch (error) {
      setError(readableError(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="panel">
      <PanelToolbar title="System audit" onRefresh={refresh} loading={loading} />
      {error !== null && <p className="error-text">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Action</th>
            <th>Target</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>{formatDate(log.created_at)}</td>
              <td>{log.action}</td>
              <td>{log.target_type}</td>
              <td>
                <code>{JSON.stringify(log.details)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function PanelToolbar({
  title,
  loading,
  onRefresh,
}: {
  title: string;
  loading: boolean;
  onRefresh: () => void | Promise<void>;
}) {
  return (
    <div className="panel-toolbar">
      <h3>{title}</h3>
      <button className="icon-button" type="button" title="Refresh" onClick={() => void onRefresh()} disabled={loading}>
        <RefreshCw size={16} />
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`status-pill ${ok ? "ok" : "warn"}`}>
      <CheckCircle2 size={14} />
      {label}
    </span>
  );
}

function viewTitle(view: View) {
  if (view === "transport") {
    return "Transport";
  }
  if (view === "config") {
    return "Config";
  }
  if (view === "users") {
    return "Users";
  }
  if (view === "audit") {
    return "Audit";
  }
  return "Status";
}

function readableError(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatBoolean(value: boolean) {
  return value ? "enabled" : "disabled";
}

function formatBytes(value: number) {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
    notation: value >= 1_000_000 ? "compact" : "standard",
  }).format(value);
}

createRoot(document.getElementById("root")!).render(<App />);
