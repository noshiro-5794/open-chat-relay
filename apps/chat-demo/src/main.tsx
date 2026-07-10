import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Check,
  CornerUpLeft,
  Edit3,
  Hash,
  Home,
  LogOut,
  MessageSquareText,
  Plus,
  RadioTower,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  UserPlus,
  UserRound,
  UsersRound,
  X,
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
  deleteMessage,
  getApiBaseUrl,
  leaveRoom,
  listMessages,
  listRoomPresence,
  listRoomMembers,
  listRooms,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  messageFromRealtimeEvent,
  register,
  searchMessages,
  setApiBaseUrl,
  updateMessage,
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
  reply_to_id: string | null;
  created_at: string;
  delivery_status: DeliveryStatus;
}

type RenderMessage = Message | PendingMessage;

interface SendMessageOptions {
  retryPendingId?: string;
  replyToId?: string | null;
}

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
  const [messageSearchQuery, setMessageSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Message[]>([]);
  const [chatView, setChatView] = useState<ChatView>("home");
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [connection, setConnection] = useState<ConnectResult | null>(null);
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const [presenceByUserId, setPresenceByUserId] = useState<Map<string, string>>(new Map());
  const [replyTarget, setReplyTarget] = useState<Message | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<OpenChatRelayClient | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openRoomSeqRef = useRef(0);
  const messageListRef = useRef<HTMLDivElement | null>(null);

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId);
  const directRooms = rooms.filter((room) => room.is_private);
  const spaceRooms = rooms.filter((room) => !room.is_private);
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const visibleDirectRooms = filterRooms(directRooms, normalizedSearch);
  const visibleSpaceRooms = filterRooms(spaceRooms, normalizedSearch);
  const visibleHomeRooms = filterRooms(rooms, normalizedSearch);
  const activeTypingUsers = [...typingUsers].filter((userId) => userId !== tokenPair?.user.id);
  const onlineUserCount = [...presenceByUserId.values()].filter((status) => status !== "offline").length;

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

  useEffect(() => {
    messageListRef.current?.scrollTo({
      top: messageListRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [groupedMessages.length, activeTypingUsers.length, selectedRoomId]);

  useEffect(
    () => () => {
      if (typingTimerRef.current !== null) {
        clearTimeout(typingTimerRef.current);
      }
    },
    [],
  );

  async function handleAuth() {
    setError(null);
    setBusyAction("auth");
    try {
      const result =
        authMode === "login"
          ? await login(email.trim(), password)
          : await register(email.trim(), password, displayName.trim() || "OpenChatRelay User");
      saveSession(result);
      setTokenPair(result);
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : "Authentication failed.");
    } finally {
      setBusyAction(null);
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
      let nextRooms = (await listRooms(token, workspaceId)).filter((room) => room.role !== null);
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
    const sequence = ++openRoomSeqRef.current;
    setMessages([]);
    setPendingMessages([]);
    setTypingUsers(new Set());
    setPresenceByUserId(new Map());
    setReplyTarget(null);
    setEditingMessageId(null);
    setEditingDraft("");
    setSearchResults([]);
    setConnectionState("connecting");
    setConnection(null);
    setError(null);
    clientRef.current?.close();
    let openingClient: OpenChatRelayClient | null = null;

    try {
      const history = await listMessages(token, roomId);
      if (sequence !== openRoomSeqRef.current) {
        return;
      }
      setMessages(history);

      const client = new OpenChatRelayClient(apiUrl);
      openingClient = client;
      client.onEvent((event) => handleRealtimeEvent(event));
      const result = await client.connect({ token });
      if (sequence !== openRoomSeqRef.current) {
        openingClient.close();
        return;
      }
      await client.subscribeRoom(roomId);
      await client.updatePresence(roomId, "online");
      await refreshPresence(token, roomId);
      if (sequence !== openRoomSeqRef.current) {
        openingClient.close();
        return;
      }
      clientRef.current = client;
      openingClient = null;
      setConnection(result);
      setConnectionState("connected");
    } catch (connectError) {
      if (sequence !== openRoomSeqRef.current) {
        openingClient?.close();
        return;
      }
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

  async function refreshPresence(token: string, roomId: string) {
    try {
      const presence = await listRoomPresence(token, roomId);
      setPresenceByUserId(
        new Map(presence.users.map((user) => [user.user_id, user.status])),
      );
    } catch {
      setPresenceByUserId(new Map());
    }
  }

  function handleRealtimeEvent(event: RealtimeEvent) {
    const message = messageFromRealtimeEvent(event);
    if (message !== null) {
      setMessages((current) => {
        if (event.type === "message.deleted") {
          return current.map((item) =>
            item.id === message.id ? { ...item, deleted_at: message.deleted_at } : item,
          );
        }
        if (event.type === "message.updated") {
          return current.map((item) =>
            item.id === message.id
              ? { ...item, content: message.content, updated_at: message.updated_at }
              : item,
          );
        }
        return current.some((item) => item.id === message.id) ? current : [...current, message];
      });
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
    if (event.type === "presence.updated") {
      const data = event.data as { user_id?: string; status?: string } | undefined;
      if (typeof data?.user_id !== "string" || typeof data.status !== "string") {
        return;
      }
      const userId = data.user_id;
      const status = data.status;
      setPresenceByUserId((current) => {
        const next = new Map(current);
        if (status === "offline") {
          next.delete(userId);
        } else {
          next.set(userId, status);
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
    setBusyAction("create-group");
    try {
      const room = await createRoom(tokenPair.access_token, selectedWorkspaceId, newSpaceName.trim());
      await refreshRooms(tokenPair.access_token, selectedWorkspaceId);
      setSelectedRoomId(room.id);
      setNewSpaceName("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create group.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleStartDirectMessage() {
    const emailToAdd = contactEmail.trim();
    if (tokenPair === null || selectedWorkspaceId === null || emailToAdd === "") {
      return;
    }
    setError(null);
    setBusyAction("add-contact");
    try {
      const member = await addWorkspaceMember(tokenPair.access_token, selectedWorkspaceId, emailToAdd);
      const existingRoom = await findDirectRoomWithMember(
        tokenPair.access_token,
        selectedWorkspaceId,
        member.user_id,
      );
      if (existingRoom !== null) {
        await refreshMembers(tokenPair.access_token, selectedWorkspaceId);
        setSelectedRoomId(existingRoom.id);
        setContactEmail("");
        return;
      }
      const room = await createDirectRoom(tokenPair.access_token, selectedWorkspaceId, member);
      await addRoomMember(tokenPair.access_token, room.id, member.user_id);
      await refreshMembers(tokenPair.access_token, selectedWorkspaceId);
      await refreshRooms(tokenPair.access_token, selectedWorkspaceId);
      setSelectedRoomId(room.id);
      setContactEmail("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to start direct message.");
    } finally {
      setBusyAction(null);
    }
  }

  async function findDirectRoomWithMember(
    token: string,
    workspaceId: string,
    userId: string,
  ): Promise<Room | null> {
    const latestRooms = await listRooms(token, workspaceId);
    setRooms(latestRooms.filter((room) => room.role !== null));
    for (const room of latestRooms.filter((item) => item.is_private)) {
      try {
        const roomMembers = await listRoomMembers(token, room.id);
        if (roomMembers.some((member) => member.user_id === userId)) {
          return room;
        }
      } catch {
        // The current user may not belong to every private room returned by the
        // workspace list yet; skip rooms whose membership cannot be inspected.
      }
    }
    return null;
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
    setBusyAction("invite-member");
    try {
      const member = await addWorkspaceMember(
        tokenPair.access_token,
        selectedWorkspaceId,
        emailToInvite,
      );
      await addRoomMember(tokenPair.access_token, selectedRoomId, member.user_id);
      await refreshMembers(tokenPair.access_token, selectedWorkspaceId);
      setInviteEmail("");
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : "Unable to invite member.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteConversation(room: Room) {
    if (tokenPair === null || selectedWorkspaceId === null) {
      return;
    }
    const conversationType = room.is_private ? "friend chat" : "group";
    if (!window.confirm(`Delete this ${conversationType} from your chat list?`)) {
      return;
    }
    setBusyAction(`leave-${room.id}`);
    setError(null);
    try {
      await leaveRoom(tokenPair.access_token, room.id);
      const remainingRooms = rooms.filter((item) => item.id !== room.id);
      setRooms(remainingRooms);
      if (selectedRoomId === room.id) {
        clientRef.current?.close();
        clientRef.current = null;
        setSelectedRoomId(remainingRooms[0]?.id ?? null);
        setMessages([]);
        setPendingMessages([]);
        setReplyTarget(null);
        setEditingMessageId(null);
        setEditingDraft("");
        setSearchResults([]);
      }
      await refreshRooms(tokenPair.access_token, selectedWorkspaceId);
    } catch (leaveError) {
      setError(leaveError instanceof Error ? leaveError.message : "Unable to delete conversation.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (content === "" || selectedRoomId === null || tokenPair === null) {
      return;
    }
    await sendMessageContent(content, { replyToId: replyTarget?.id ?? null });
  }

  async function sendMessageContent(content: string, options: SendMessageOptions = {}) {
    if (content === "" || selectedRoomId === null || tokenPair === null) {
      return;
    }
    const pendingId = createLocalId();
    const activePendingId = options.retryPendingId ?? pendingId;
    if (options.retryPendingId === undefined) {
      const pendingMessage: PendingMessage = {
        id: pendingId,
        room_id: selectedRoomId,
        sender_id: tokenPair.user.id,
        content,
        reply_to_id: options.replyToId ?? null,
        created_at: new Date().toISOString(),
        delivery_status: "sending",
      };
      setPendingMessages((current) => [...current, pendingMessage]);
      setDraft("");
      setReplyTarget(null);
    } else {
      setPendingMessages((current) =>
        current.map((message) =>
          message.id === options.retryPendingId
            ? { ...message, delivery_status: "sending" }
            : message,
        ),
      );
    }
    setError(null);
    try {
      if (connectionState === "connected" && clientRef.current !== null) {
        try {
          await clientRef.current.sendMessage(selectedRoomId, content, {
            replyToId: options.replyToId ?? undefined,
          });
          await clientRef.current.updateTyping(selectedRoomId, "stopped");
          setPendingMessages((current) => current.filter((message) => message.id !== activePendingId));
          setMessages(await listMessages(tokenPair.access_token, selectedRoomId));
          return;
        } catch {
          // Fall back to the durable HTTP path below; the demo should stay usable
          // even when the realtime command channel is reconnecting.
        }
      }

      const message = await createMessage(tokenPair.access_token, selectedRoomId, content, {
        replyToId: options.replyToId,
      });
      setPendingMessages((current) => current.filter((item) => item.id !== activePendingId));
      setMessages((current) =>
        current.some((item) => item.id === message.id) ? current : [...current, message],
      );
    } catch (sendError) {
      setPendingMessages((current) =>
        current.map((message) =>
          message.id === activePendingId ? { ...message, delivery_status: "failed" } : message,
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

  async function handleRefreshChat() {
    if (tokenPair === null || selectedWorkspaceId === null) {
      return;
    }
    setBusyAction("refresh");
    setError(null);
    try {
      await refreshMembers(tokenPair.access_token, selectedWorkspaceId);
      await refreshRooms(tokenPair.access_token, selectedWorkspaceId);
      if (selectedRoomId !== null) {
        setMessages(await listMessages(tokenPair.access_token, selectedRoomId));
        await refreshPresence(tokenPair.access_token, selectedRoomId);
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Unable to refresh chat.");
    } finally {
      setBusyAction(null);
    }
  }

  function handleReconnect() {
    if (tokenPair === null || selectedRoomId === null) {
      return;
    }
    void openRoom(tokenPair.access_token, selectedRoomId);
  }

  async function handleSearchMessages() {
    const query = messageSearchQuery.trim();
    if (tokenPair === null || selectedRoomId === null || query.length < 2) {
      setSearchResults([]);
      return;
    }
    setBusyAction("message-search");
    setError(null);
    try {
      setSearchResults(await searchMessages(tokenPair.access_token, selectedRoomId, query));
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Unable to search messages.");
    } finally {
      setBusyAction(null);
    }
  }

  function handleStartEdit(message: Message) {
    setReplyTarget(null);
    setEditingMessageId(message.id);
    setEditingDraft(message.content);
  }

  async function handleSaveEdit(message: Message) {
    const content = editingDraft.trim();
    if (tokenPair === null || selectedRoomId === null || content === "") {
      return;
    }
    setBusyAction(`edit-${message.id}`);
    setError(null);
    try {
      const updatedMessage = await updateMessage(
        tokenPair.access_token,
        selectedRoomId,
        message.id,
        content,
      );
      setMessages((current) =>
        current.map((item) => (item.id === message.id ? updatedMessage : item)),
      );
      setEditingMessageId(null);
      setEditingDraft("");
    } catch (editError) {
      setError(editError instanceof Error ? editError.message : "Unable to edit message.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteMessage(message: Message) {
    if (tokenPair === null || selectedRoomId === null || !window.confirm("Delete this message?")) {
      return;
    }
    setBusyAction(`delete-${message.id}`);
    setError(null);
    try {
      const deletedMessage = await deleteMessage(tokenPair.access_token, selectedRoomId, message.id);
      setMessages((current) =>
        current.map((item) => (item.id === message.id ? deletedMessage : item)),
      );
      if (replyTarget?.id === message.id) {
        setReplyTarget(null);
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete message.");
    } finally {
      setBusyAction(null);
    }
  }

  function handleJumpToMessage(message: Message) {
    setSearchResults([]);
    if (!messages.some((item) => item.id === message.id)) {
      setMessages((current) => [...current, message].sort(byCreatedAt));
    }
    window.setTimeout(() => {
      document
        .querySelector(`[data-message-id="${CSS.escape(message.id)}"]`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 50);
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
    setMessageSearchQuery("");
    setSearchResults([]);
    setReplyTarget(null);
    setEditingMessageId(null);
    setEditingDraft("");
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
          <button
            className="primary-action"
            onClick={() => void handleAuth()}
            disabled={busyAction === "auth"}
          >
            <ShieldCheck size={18} />
            {busyAction === "auth" ? "Connecting..." : "Continue"}
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
            <div key={room.id} className={room.id === selectedRoomId ? "room-row active" : "room-row"}>
              <button
                className={room.id === selectedRoomId ? "room active" : "room"}
                onClick={() => setSelectedRoomId(room.id)}
              >
                {room.is_private ? <UserRound size={16} /> : <Hash size={16} />}
                {room.name}
              </button>
              <button
                className="icon-button room-delete"
                title={`Delete ${room.is_private ? "friend chat" : "group"}`}
                disabled={busyAction === `leave-${room.id}`}
                onClick={() => void handleDeleteConversation(room)}
              >
                <Trash2 size={15} />
              </button>
            </div>
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
            disabled={busyAction === "add-contact" || contactEmail.trim() === ""}
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
          <button
            className="icon-button"
            title="Create group"
            disabled={busyAction === "create-group" || newSpaceName.trim() === ""}
            onClick={() => void handleCreateSpace()}
          >
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
              disabled={busyAction === "invite-member" || inviteEmail.trim() === ""}
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
                  ? `${onlineUserCount} online in private chat`
                  : `${onlineUserCount} online in group chat`}
            </p>
          </div>
          <div className="conversation-actions">
            <span className={`connection-chip ${connectionState}`}>
              <RadioTower size={15} />
              {protocolStateLabel(connectionState)}
            </span>
            <button
              className="icon-button"
              title="Refresh chat"
              disabled={busyAction === "refresh" || selectedRoom === undefined}
              onClick={() => void handleRefreshChat()}
            >
              <RefreshCw size={17} />
            </button>
            <button
              className="secondary-action reconnect-action"
              disabled={selectedRoom === undefined || connectionState === "connecting"}
              onClick={handleReconnect}
            >
              Reconnect
            </button>
          </div>
        </header>

        <div className="conversation-search">
          <Search size={15} />
          <input
            value={messageSearchQuery}
            placeholder="Search in this chat"
            onChange={(event) => setMessageSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void handleSearchMessages();
              }
            }}
          />
          <button
            className="secondary-action search-action"
            disabled={
              selectedRoom === undefined ||
              messageSearchQuery.trim().length < 2 ||
              busyAction === "message-search"
            }
            onClick={() => void handleSearchMessages()}
          >
            Search
          </button>
        </div>

        {searchResults.length > 0 && (
          <div className="search-results">
            {searchResults.map((message) => (
              <button key={message.id} onClick={() => handleJumpToMessage(message)}>
                <strong>{senderName(message, tokenPair.user, members)}</strong>
                <span>{message.deleted_at === null ? message.content : "Message deleted"}</span>
              </button>
            ))}
          </div>
        )}

        {error !== null && <div className="inline-error">{error}</div>}

        <div className="message-list" ref={messageListRef}>
          {selectedRoom === undefined ? (
            <div className="empty-state">
              <MessageSquareText size={34} />
              <h3>Start a conversation</h3>
              <p>Add a friend by email or create a group to begin.</p>
            </div>
          ) : (
            <>
              {groupedMessages.map((message) => {
                const isPending = isPendingMessage(message);
                const isDeleted = !isPending && message.deleted_at !== null;
                const isMine = message.sender_id === tokenPair.user.id;
                const replyPreview =
                  message.reply_to_id === null
                    ? undefined
                    : messages.find((item) => item.id === message.reply_to_id);
                return (
                  <article
                    key={message.id}
                    data-message-id={message.id}
                    className={isMine ? "message mine" : "message"}
                  >
                    <div className="avatar">
                      <UserRound size={17} />
                    </div>
                    <div className="bubble">
                      <div className="message-meta">
                        <strong>{senderName(message, tokenPair.user, members)}</strong>
                        <span>{formatTime(message.created_at)}</span>
                        {!isPending && message.updated_at !== message.created_at && !isDeleted && (
                          <span>Edited</span>
                        )}
                        {isPending && (
                          <span className={`delivery-status ${message.delivery_status}`}>
                            {message.delivery_status === "sending" ? (
                              "Sending..."
                            ) : (
                              <button
                                className="retry-button"
                                onClick={() =>
                                  void sendMessageContent(message.content, {
                                    retryPendingId: message.id,
                                    replyToId: message.reply_to_id,
                                  })
                                }
                              >
                                Retry
                              </button>
                            )}
                          </span>
                        )}
                      </div>
                      {replyPreview !== undefined && (
                        <button
                          className="reply-preview"
                          onClick={() => handleJumpToMessage(replyPreview)}
                        >
                          <CornerUpLeft size={13} />
                          <span>{messageSummary(replyPreview)}</span>
                        </button>
                      )}
                      {!isPending && editingMessageId === message.id ? (
                        <div className="edit-box">
                          <textarea
                            value={editingDraft}
                            onChange={(event) => setEditingDraft(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                void handleSaveEdit(message);
                              }
                            }}
                          />
                          <div>
                            <button
                              className="icon-button"
                              title="Save edit"
                              disabled={
                                editingDraft.trim() === "" || busyAction === `edit-${message.id}`
                              }
                              onClick={() => void handleSaveEdit(message)}
                            >
                              <Check size={16} />
                            </button>
                            <button
                              className="icon-button"
                              title="Cancel edit"
                              onClick={() => {
                                setEditingMessageId(null);
                                setEditingDraft("");
                              }}
                            >
                              <X size={16} />
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p>{isDeleted ? "Message deleted" : message.content}</p>
                      )}
                      {!isPending && !isDeleted && (
                        <div className="message-actions">
                          <button title="Reply" onClick={() => setReplyTarget(message)}>
                            <CornerUpLeft size={14} />
                            Reply
                          </button>
                          {isMine && (
                            <>
                              <button title="Edit" onClick={() => handleStartEdit(message)}>
                                <Edit3 size={14} />
                                Edit
                              </button>
                              <button
                                title="Delete"
                                disabled={busyAction === `delete-${message.id}`}
                                onClick={() => void handleDeleteMessage(message)}
                              >
                                <Trash2 size={14} />
                                Delete
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
              {activeTypingUsers.length > 0 && (
                <div className="typing-row">{typingLabel(activeTypingUsers, members)} typing...</div>
              )}
            </>
          )}
        </div>

        {selectedRoom !== undefined && (
          <footer className="composer">
            {replyTarget !== null && (
              <div className="composer-reply">
                <CornerUpLeft size={15} />
                <span>{messageSummary(replyTarget)}</span>
                <button className="icon-button" title="Cancel reply" onClick={() => setReplyTarget(null)}>
                  <X size={15} />
                </button>
              </div>
            )}
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
            <dt>Online</dt>
            <dd>{onlineUserCount}</dd>
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

function typingLabel(userIds: string[], members: WorkspaceMember[]): string {
  const names = userIds.map((userId) => {
    const member = members.find((item) => item.user_id === userId);
    return member?.display_name ?? "Someone";
  });
  if (names.length === 1) {
    return names[0];
  }
  if (names.length === 2) {
    return `${names[0]} and ${names[1]}`;
  }
  return `${names[0]} and ${names.length - 1} others`;
}

function messageSummary(message: Message): string {
  if (message.deleted_at !== null) {
    return "Message deleted";
  }
  return message.content.length > 96 ? `${message.content.slice(0, 96)}...` : message.content;
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
