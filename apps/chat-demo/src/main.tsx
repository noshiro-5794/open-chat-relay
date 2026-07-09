import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Hash,
  Home,
  LogOut,
  MessageSquareText,
  Plus,
  RadioTower,
  Search,
  Send,
  ShieldCheck,
  UserPlus,
  UserRound,
  UsersRound,
} from "lucide-react";

import {
  OpenChatRelayClient,
  RealtimeConnectError,
  type ConnectResult,
  type RealtimeEvent,
} from "@openchatrelay/sdk";
import {
  ApiError,
  type Message,
  type Room,
  type TokenPair,
  type Workspace,
  type WorkspaceMember,
  addRoomMember,
  addWorkspaceMember,
  createMessage,
  createRoom,
  createWorkspace,
  getApiBaseUrl,
  listMessages,
  listRooms,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  messageFromRealtimeEvent,
  register,
  setApiBaseUrl,
} from "./api";
import "./styles.css";

type AuthMode = "login" | "register";
type ConnectionState = "idle" | "connecting" | "connected" | "failed";
type ChatView = "home" | "friends" | "groups";
type DeliveryStatus = "sending" | "failed";

interface PendingMessage {
  id: string;
  room_id: string;
  sender_id: string;
  content: string;
  created_at: string;
  delivery_status: DeliveryStatus;
}

type RenderMessage = Message | PendingMessage;

const TOKEN_STORAGE_KEY = "openchatrelay.demo.token";
const USER_STORAGE_KEY = "openchatrelay.demo.user";
const API_BASE_STORAGE_KEY = "openchatrelay.demo.apiBaseUrl";
const STALE_LOCAL_API_URLS = new Set([
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://localhost:18000",
  "http://127.0.0.1:18000",
]);

function App() {
  const [apiUrl, setApiUrl] = useState(() => loadApiBaseUrl());
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("demo@openchatrelay.dev");
  const [password, setPassword] = useState("correct horse battery staple");
  const [displayName, setDisplayName] = useState("Demo User");
  const [tokenPair, setTokenPair] = useState<TokenPair | null>(() => loadSession());
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pendingMessages, setPendingMessages] = useState<PendingMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [newSpaceName, setNewSpaceName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [chatView, setChatView] = useState<ChatView>("home");
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [connection, setConnection] = useState<ConnectResult | null>(null);
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<OpenChatRelayClient | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId);
  const directRooms = rooms.filter((room) => room.is_private);
  const spaceRooms = rooms.filter((room) => !room.is_private);
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const visibleDirectRooms = filterRooms(directRooms, normalizedSearch);
  const visibleSpaceRooms = filterRooms(spaceRooms, normalizedSearch);
  const visibleHomeRooms = filterRooms(rooms, normalizedSearch);

  useEffect(() => {
    setApiBaseUrl(apiUrl);
    localStorage.setItem(API_BASE_STORAGE_KEY, apiUrl);
  }, [apiUrl]);

  useEffect(() => {
    if (tokenPair === null) {
      return;
    }
    void loadSpaces(tokenPair.access_token, tokenPair.user);
  }, [tokenPair]);

  useEffect(() => {
    if (tokenPair === null || selectedWorkspaceId === null) {
      return;
    }
    void refreshRooms(tokenPair.access_token, selectedWorkspaceId);
    void refreshMembers(tokenPair.access_token, selectedWorkspaceId);
  }, [selectedWorkspaceId, tokenPair]);

  useEffect(() => {
    if (tokenPair === null || selectedRoomId === null) {
      return;
    }
    void openRoom(tokenPair.access_token, selectedRoomId);
    return () => {
      clientRef.current?.close();
      clientRef.current = null;
    };
  }, [selectedRoomId, tokenPair]);

  const groupedMessages = useMemo(
    () => [...messages, ...pendingMessages].sort(byCreatedAt),
    [messages, pendingMessages],
  );

  async function handleAuth() {
    setError(null);
    try {
      const result =
        authMode === "login"
          ? await login(email.trim(), password)
          : await register(email.trim(), password, displayName.trim() || "OpenChatRelay User");
      saveSession(result);
      setTokenPair(result);
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Authentication failed.");
    }
  }

  async function loadSpaces(token: string, user: TokenPair["user"]) {
    setError(null);
    try {
      let nextWorkspaces = await listWorkspaces(token);
      if (nextWorkspaces.length === 0) {
        nextWorkspaces = [await createDemoWorkspace(token, user)];
      }
      setWorkspaces(nextWorkspaces);
      setSelectedWorkspaceId((current) => current ?? nextWorkspaces[0]?.id ?? null);
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 401) {
        expireSession();
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Unable to load workspaces.");
    }
  }

  async function createDemoWorkspace(token: string, user: TokenPair["user"]): Promise<Workspace> {
    const baseName = `${user.display_name || "Demo User"} Workspace`;
    try {
      return await createWorkspace(token, baseName);
    } catch (createError) {
      if (!(createError instanceof ApiError) || createError.status !== 409) {
        throw createError;
      }
    }

    return createWorkspace(token, `OpenChatRelay Demo ${user.id.slice(0, 8)}`);
  }

  async function refreshRooms(token: string, workspaceId: string) {
    setError(null);
    try {
      let nextRooms = await listRooms(token, workspaceId);
      if (nextRooms.length === 0) {
        nextRooms = [await createRoom(token, workspaceId, "General")];
      }
      setRooms(nextRooms);
      setSelectedRoomId((current) =>
        current !== null && nextRooms.some((room) => room.id === current)
          ? current
          : nextRooms[0]?.id ?? null,
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load rooms.");
    }
  }

  async function refreshMembers(token: string, workspaceId: string) {
    try {
      setMembers(await listWorkspaceMembers(token, workspaceId));
    } catch {
      setMembers([]);
    }
  }

  async function openRoom(token: string, roomId: string) {
    setMessages([]);
    setPendingMessages([]);
    setTypingUsers(new Set());
    setConnectionState("connecting");
    setConnection(null);
    clientRef.current?.close();
    let openingClient: OpenChatRelayClient | null = null;

    try {
      const history = await listMessages(token, roomId);
      setMessages(history);

      const client = new OpenChatRelayClient(apiUrl);
      openingClient = client;
      client.onEvent((event) => handleRealtimeEvent(event));
      const result = await client.connect({ token });
      await client.subscribeRoom(roomId);
      await client.updatePresence(roomId, "online");
      clientRef.current = client;
      openingClient = null;
      setConnection(result);
      setConnectionState("connected");
    } catch (connectError) {
      openingClient?.close();
      clientRef.current?.close();
      clientRef.current = null;
      setConnectionState("failed");
      setError(
        connectError instanceof RealtimeConnectError
          ? "Realtime connection failed after trying all transports."
          : connectError instanceof Error
            ? connectError.message
            : "Unable to open room.",
      );
    }
  }

  function handleRealtimeEvent(event: RealtimeEvent) {
    const message = messageFromRealtimeEvent(event);
    if (message !== null) {
      setMessages((current) =>
        current.some((item) => item.id === message.id) ? current : [...current, message],
      );
      return;
    }
    if (event.type === "typing.updated" && typeof event.actor_id === "string") {
      const actorId = event.actor_id;
      const data = event.data as { status?: string } | undefined;
      setTypingUsers((current) => {
        const next = new Set(current);
        if (data?.status === "started") {
          next.add(actorId);
        } else {
          next.delete(actorId);
        }
        return next;
      });
    }
  }

  async function handleCreateSpace() {
    if (tokenPair === null || selectedWorkspaceId === null || newSpaceName.trim() === "") {
      return;
    }
    setError(null);
    try {
      const room = await createRoom(tokenPair.access_token, selectedWorkspaceId, newSpaceName.trim());
      setRooms((current) => [...current, room]);
      setSelectedRoomId(room.id);
      setNewSpaceName("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create group.");
    }
  }

  async function handleStartDirectMessage() {
    const emailToAdd = contactEmail.trim();
    if (tokenPair === null || selectedWorkspaceId === null || emailToAdd === "") {
      return;
    }
    setError(null);
    try {
      const member = await addWorkspaceMember(tokenPair.access_token, selectedWorkspaceId, emailToAdd);
      const room = await createDirectRoom(tokenPair.access_token, selectedWorkspaceId, member);
      await addRoomMember(tokenPair.access_token, room.id, member.user_id);
      setMembers((current) =>
        current.some((item) => item.user_id === member.user_id) ? current : [...current, member],
      );
      setRooms((current) => [...current, room]);
      setSelectedRoomId(room.id);
      setContactEmail("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to start direct message.");
    }
  }

  async function createDirectRoom(
    token: string,
    workspaceId: string,
    member: WorkspaceMember,
  ): Promise<Room> {
    const primaryName = `${tokenPair?.user.display_name ?? "You"} and ${member.display_name}`;
    try {
      return await createRoom(token, workspaceId, primaryName, { isPrivate: true });
    } catch (createError) {
      if (!(createError instanceof ApiError) || createError.status !== 409) {
        throw createError;
      }
    }
    return createRoom(token, workspaceId, `${member.display_name} ${member.user_id.slice(0, 8)}`, {
      isPrivate: true,
    });
  }

  async function handleInviteMember() {
    const emailToInvite = inviteEmail.trim();
    if (
      tokenPair === null ||
      selectedWorkspaceId === null ||
      selectedRoomId === null ||
      emailToInvite === ""
    ) {
      return;
    }
    setError(null);
    try {
      const member = await addWorkspaceMember(
        tokenPair.access_token,
        selectedWorkspaceId,
        emailToInvite,
      );
      await addRoomMember(tokenPair.access_token, selectedRoomId, member.user_id);
      setInviteEmail("");
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : "Unable to invite member.");
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (content === "" || selectedRoomId === null || tokenPair === null) {
      return;
    }
    const pendingId = createLocalId();
    const pendingMessage: PendingMessage = {
      id: pendingId,
      room_id: selectedRoomId,
      sender_id: tokenPair.user.id,
      content,
      created_at: new Date().toISOString(),
      delivery_status: "sending",
    };
    setPendingMessages((current) => [...current, pendingMessage]);
    setDraft("");
    setError(null);
    try {
      if (connectionState === "connected" && clientRef.current !== null) {
        try {
          await clientRef.current.sendMessage(selectedRoomId, content);
          await clientRef.current.updateTyping(selectedRoomId, "stopped");
          setPendingMessages((current) => current.filter((message) => message.id !== pendingId));
          setMessages(await listMessages(tokenPair.access_token, selectedRoomId));
          return;
        } catch {
          // Fall back to the durable HTTP path below; the demo should stay usable
          // even when the realtime command channel is reconnecting.
        }
      }

      const message = await createMessage(tokenPair.access_token, selectedRoomId, content);
      setPendingMessages((current) => current.filter((item) => item.id !== pendingId));
      setMessages((current) =>
        current.some((item) => item.id === message.id) ? current : [...current, message],
      );
    } catch (sendError) {
      setPendingMessages((current) =>
        current.map((message) =>
          message.id === pendingId ? { ...message, delivery_status: "failed" } : message,
        ),
      );
      setError(sendError instanceof Error ? sendError.message : "Unable to send message.");
    }
  }

  function handleDraftChange(value: string) {
    setDraft(value);
    if (selectedRoomId === null || connectionState !== "connected" || clientRef.current === null) {
      return;
    }
    void clientRef.current.updateTyping(selectedRoomId, "started").catch(() => undefined);
    if (typingTimerRef.current !== null) {
      clearTimeout(typingTimerRef.current);
    }
    typingTimerRef.current = setTimeout(() => {
      if (selectedRoomId !== null) {
        void clientRef.current?.updateTyping(selectedRoomId, "stopped").catch(() => undefined);
      }
    }, 1200);
  }

  function handleSignOut() {
    clearSessionState();
  }

  function expireSession() {
    clearSessionState();
    setError("Session expired. Sign in again.");
  }

  function clearSessionState() {
    clientRef.current?.close();
    clientRef.current = null;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    setTokenPair(null);
    setWorkspaces([]);
    setRooms([]);
    setMembers([]);
    setMessages([]);
    setPendingMessages([]);
    setNewSpaceName("");
    setContactEmail("");
    setInviteEmail("");
    setSelectedRoomId(null);
    setSelectedWorkspaceId(null);
    setConnectionState("idle");
    setError(null);
  }

  if (tokenPair === null) {
    return (
      <main className="auth-shell">
        <section className="auth-panel">
          <div className="brand-mark">
            <RadioTower size={24} />
          </div>
          <h1>OpenChatRelay</h1>
          <p>Multi-transport communication demo for web and Windows clients.</p>
          <div className="segmented">
            <button className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")}>
              Sign in
            </button>
            <button
              className={authMode === "register" ? "active" : ""}
              onClick={() => setAuthMode("register")}
            >
              Register
            </button>
          </div>
          <label>
            Server
            <input
              value={apiUrl}
              onChange={(event) => setApiUrl(event.target.value)}
              placeholder="https://api.chat.example.com"
            />
          </label>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          {authMode === "register" && (
            <label>
              Display name
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
          )}
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error !== null && <div className="error">{error}</div>}
          <button className="primary-action" onClick={() => void handleAuth()}>
            <ShieldCheck size={18} />
            Continue
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <header className="sidebar-header">
          <div>
            <span className="eyebrow">OpenChatRelay</span>
            <strong>Chats</strong>
          </div>
          <button className="icon-button" title="Sign out" onClick={handleSignOut}>
            <LogOut size={18} />
          </button>
        </header>

        <div className="search-box">
          <Search size={16} />
          <input
            value={searchQuery}
            placeholder="Find people and spaces"
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </div>

        <div className="sidebar-nav">
          <button className={chatView === "home" ? "active" : ""} onClick={() => setChatView("home")}>
            <Home size={16} />
            Home
          </button>
          <button
            className={chatView === "friends" ? "active" : ""}
            onClick={() => setChatView("friends")}
          >
            <UserRound size={16} />
            Friends
          </button>
          <button
            className={chatView === "groups" ? "active" : ""}
            onClick={() => setChatView("groups")}
          >
            <UsersRound size={16} />
            Groups
          </button>
        </div>

        <div className="room-section">
          <div className="section-title">
            {chatView === "home" ? "Recent chats" : chatView === "friends" ? "Friends" : "Groups"}
          </div>
          {(chatView === "home"
            ? visibleHomeRooms
            : chatView === "friends"
              ? visibleDirectRooms
              : visibleSpaceRooms
          ).map((room) => (
              <button
                key={room.id}
                className={room.id === selectedRoomId ? "room active" : "room"}
                onClick={() => setSelectedRoomId(room.id)}
              >
                {room.is_private ? <UserRound size={16} /> : <Hash size={16} />}
                {room.name}
              </button>
            ))}
          {chatView === "friends" && directRooms.length === 0 && (
            <div className="empty-list">Add a friend to start chatting.</div>
          )}
          {chatView === "groups" && spaceRooms.length === 0 && (
            <div className="empty-list">Create a group to start collaborating.</div>
          )}
        </div>

        <div className="new-room contact-entry">
          <input
            placeholder="Add contact by email"
            value={contactEmail}
            onChange={(event) => setContactEmail(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void handleStartDirectMessage();
              }
            }}
          />
          <button
            className="icon-button"
            title="Start direct message"
            onClick={() => void handleStartDirectMessage()}
          >
            <UserPlus size={18} />
          </button>
        </div>

        <div className="new-room">
          <input
            placeholder="New group"
            value={newSpaceName}
            onChange={(event) => setNewSpaceName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void handleCreateSpace();
              }
            }}
          />
          <button className="icon-button" title="Create group" onClick={() => void handleCreateSpace()}>
            <Plus size={18} />
          </button>
        </div>

        {selectedRoom !== undefined && !selectedRoom.is_private && (
          <div className="new-room group-member-entry">
            <input
              value={inviteEmail}
              placeholder="Add member to group"
              onChange={(event) => setInviteEmail(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void handleInviteMember();
                }
              }}
            />
            <button
              className="icon-button"
              title="Add member to selected group"
              onClick={() => void handleInviteMember()}
            >
              <UserPlus size={18} />
            </button>
          </div>
        )}
      </aside>

      <section className="conversation">
        <header className="conversation-header">
          <div>
            <h2>{selectedRoom?.name ?? "Select a chat"}</h2>
            <p>
              {selectedRoom === undefined
                ? "Choose a friend or group"
                : selectedRoom.is_private
                  ? "Private chat"
                  : "Group chat"}
            </p>
          </div>
        </header>

        {error !== null && <div className="inline-error">{error}</div>}

        <div className="message-list">
          {selectedRoom === undefined ? (
            <div className="empty-state">
              <MessageSquareText size={34} />
              <h3>Start a conversation</h3>
              <p>Add a friend by email or create a group to begin.</p>
            </div>
          ) : (
            <>
              {groupedMessages.map((message) => (
                <article
                  key={message.id}
                  className={message.sender_id === tokenPair.user.id ? "message mine" : "message"}
                >
                  <div className="avatar">
                    <UserRound size={17} />
                  </div>
                  <div className="bubble">
                    <div className="message-meta">
                      <strong>{senderName(message, tokenPair.user, members)}</strong>
                      <span>{formatTime(message.created_at)}</span>
                      {isPendingMessage(message) && (
                        <span className={`delivery-status ${message.delivery_status}`}>
                          {message.delivery_status === "sending" ? "Sending..." : "Failed"}
                        </span>
                      )}
                    </div>
                    <p>
                      {isPendingMessage(message) || message.deleted_at === null
                        ? message.content
                        : "Message deleted"}
                    </p>
                  </div>
                </article>
              ))}
              {typingUsers.size > 0 && <div className="typing-row">Someone is typing...</div>}
            </>
          )}
        </div>

        {selectedRoom !== undefined && (
          <footer className="composer">
            <textarea
              value={draft}
              placeholder={`Message ${selectedRoom.is_private ? selectedRoom.name : `#${selectedRoom.name}`}`}
              onChange={(event) => handleDraftChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
            />
            <button
              className="send-button"
              onClick={() => void handleSend()}
              disabled={draft.trim() === "" || selectedRoomId === null}
            >
              <Send size={18} />
            </button>
          </footer>
        )}
      </section>

      <aside className="protocol-panel">
        <section className="protocol-card">
          <div className="panel-title">
            <RadioTower size={17} />
            Protocol
          </div>
          <div className={`protocol-summary ${connectionState}`}>
            <span>{protocolStateLabel(connectionState)}</span>
            <strong>{connection?.transport ?? "Waiting"}</strong>
          </div>
          <dl className="protocol-list">
            <dt>Realtime</dt>
            <dd>{connectionState === "connected" ? "Ready" : protocolStateLabel(connectionState)}</dd>
            <dt>Frame</dt>
            <dd>JSONL</dd>
            <dt>Fallback</dt>
            <dd>{connection?.skipped.length ? `${connection.skipped.length} skipped` : "None"}</dd>
          </dl>
        </section>
        <section className="protocol-card compact">
          <div className="panel-title">
            <UsersRound size={17} />
            Chat
          </div>
          <dl className="protocol-list">
            <dt>People</dt>
            <dd>{members.length}</dd>
            <dt>Type</dt>
            <dd>
              {selectedRoom === undefined ? "None" : selectedRoom.is_private ? "Private" : "Group"}
            </dd>
          </dl>
        </section>
      </aside>

    </main>
  );
}

function saveSession(tokenPair: TokenPair) {
  localStorage.setItem(TOKEN_STORAGE_KEY, tokenPair.access_token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(tokenPair.user));
}

function loadSession(): TokenPair | null {
  const accessToken = localStorage.getItem(TOKEN_STORAGE_KEY);
  const rawUser = localStorage.getItem(USER_STORAGE_KEY);
  if (accessToken === null || rawUser === null) {
    return null;
  }
  try {
    return {
      access_token: accessToken,
      refresh_token: "",
      token_type: "bearer",
      user: JSON.parse(rawUser) as TokenPair["user"],
    };
  } catch {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    return null;
  }
}

function loadApiBaseUrl(): string {
  const configuredApiBaseUrl = getApiBaseUrl();
  const storedApiBaseUrl = localStorage.getItem(API_BASE_STORAGE_KEY);
  if (storedApiBaseUrl === null || STALE_LOCAL_API_URLS.has(storedApiBaseUrl)) {
    return configuredApiBaseUrl;
  }
  return storedApiBaseUrl;
}

function byCreatedAt(left: RenderMessage, right: RenderMessage) {
  return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
}

function isPendingMessage(message: RenderMessage): message is PendingMessage {
  return "delivery_status" in message;
}

function senderName(
  message: RenderMessage,
  currentUser: TokenPair["user"],
  members: WorkspaceMember[],
): string {
  if (message.sender_id === currentUser.id) {
    return currentUser.display_name || "You";
  }
  const member = members.find((item) => item.user_id === message.sender_id);
  return member?.display_name ?? "Unknown";
}

function filterRooms(rooms: Room[], query: string): Room[] {
  if (query === "") {
    return rooms;
  }
  return rooms.filter((room) => room.name.toLowerCase().includes(query));
}

function createLocalId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function protocolStateLabel(state: ConnectionState): string {
  if (state === "connected") {
    return "Connected";
  }
  if (state === "connecting") {
    return "Connecting";
  }
  if (state === "failed") {
    return "Offline";
  }
  return "Idle";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(<App />);
