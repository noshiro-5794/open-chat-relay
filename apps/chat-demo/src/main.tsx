import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Check,
  CornerUpLeft,
  Download,
  Edit3,
  Hash,
  Home,
  LogOut,
  MessageSquareText,
  Paperclip,
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
  type Attachment,
  type Friend,
  type Message,
  type Room,
  type RoomMember,
  type TokenPair,
  type User,
  addFriend,
  confirmAttachmentUpload,
  createAttachmentDownloadIntent,
  createAttachmentUploadIntent,
  createGroupConversation,
  createMessage,
  deleteMessage,
  getApiBaseUrl,
  leaveRoom,
  inviteRoomMember,
  listConversations,
  listFriends,
  listMessages,
  listRoomPresence,
  listRoomMembers,
  listUsers,
  login,
  messageFromRealtimeEvent,
  register,
  searchMessages,
  setApiBaseUrl,
  startGlobalDirectConversation,
  updateMe,
  updateMessage,
  uploadAttachmentObject,
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
  attachment_ids: string[];
  attachment_names: string[];
  created_at: string;
  delivery_status: DeliveryStatus;
}

type RenderMessage = Message | PendingMessage;

interface SendMessageOptions {
  retryPendingId?: string;
  replyToId?: string | null;
  attachmentIds?: string[];
  attachmentNames?: string[];
}

interface AttachmentDraft {
  id: string;
  file: File;
}

const TOKEN_STORAGE_KEY = "openchatrelay.demo.token";
const USER_STORAGE_KEY = "openchatrelay.demo.user";
const API_BASE_STORAGE_KEY = "openchatrelay.demo.apiBaseUrl";
const QUICK_EMOJIS = ["👍", "😀", "🎉", "❤️", "🙏", "😂", "🔥", "✅"];
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
  const [rooms, setRooms] = useState<Room[]>([]);
  const [members, setMembers] = useState<RoomMember[]>([]);
  const [friends, setFriends] = useState<Friend[]>([]);
  const [serverUsers, setServerUsers] = useState<User[]>([]);
  const [selectedRoomId, setSelectedRoomId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pendingMessages, setPendingMessages] = useState<PendingMessage[]>([]);
  const [attachmentDrafts, setAttachmentDrafts] = useState<AttachmentDraft[]>([]);
  const [draft, setDraft] = useState("");
  const [newSpaceName, setNewSpaceName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [profileName, setProfileName] = useState(() => loadSession()?.user.display_name ?? "");
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId);
  const directRooms = rooms.filter((room) => room.is_private);
  const spaceRooms = rooms.filter((room) => !room.is_private);
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const visibleDirectRooms = filterRooms(directRooms, normalizedSearch);
  const visibleSpaceRooms = filterRooms(spaceRooms, normalizedSearch);
  const visibleHomeRooms = filterRooms(rooms, normalizedSearch);
  const visibleFriends = filterFriends(friends, normalizedSearch);
  const visibleServerUsers = filterUsers(serverUsers, normalizedSearch, tokenPair?.user.id);
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
    setProfileName(tokenPair.user.display_name);
    void refreshConversations(tokenPair.access_token);
    void refreshFriends(tokenPair.access_token);
    void refreshUsers(tokenPair.access_token);
  }, [tokenPair]);

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

  async function refreshConversations(token: string) {
    setError(null);
    try {
      const response = await listConversations(token);
      const nextRooms = response.conversations;
      setRooms(nextRooms);
      setSelectedRoomId((current) =>
        current !== null && nextRooms.some((room) => room.id === current)
          ? current
          : response.selected_conversation_id ?? nextRooms[0]?.id ?? null,
      );
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 401) {
        expireSession();
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Unable to load conversations.");
    }
  }

  async function refreshUsers(token: string) {
    try {
      setServerUsers(await listUsers(token));
    } catch {
      setServerUsers([]);
    }
  }

  async function refreshFriends(token: string) {
    try {
      setFriends(await listFriends(token));
    } catch {
      setFriends([]);
    }
  }

  async function handleSaveProfile() {
    const nextName = profileName.trim();
    if (tokenPair === null || nextName === "" || nextName === tokenPair.user.display_name) {
      return;
    }
    setBusyAction("profile");
    setError(null);
    try {
      const user = await updateMe(tokenPair.access_token, nextName);
      const nextTokenPair = { ...tokenPair, user };
      saveSession(nextTokenPair);
      setTokenPair(nextTokenPair);
      setServerUsers((current) =>
        current.map((item) => (item.id === user.id ? user : item)),
      );
    } catch (profileError) {
      setError(profileError instanceof Error ? profileError.message : "Unable to update profile.");
    } finally {
      setBusyAction(null);
    }
  }

  async function openRoom(token: string, roomId: string) {
    const sequence = ++openRoomSeqRef.current;
    setMessages([]);
    setPendingMessages([]);
    setAttachmentDrafts([]);
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
      setMembers(await listRoomMembers(token, roomId));

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
      if (event.type === "message.deleted") {
        setSearchResults((current) =>
          current.map((item) =>
            item.id === message.id ? { ...item, deleted_at: message.deleted_at } : item,
          ),
        );
        setReplyTarget((current) => (current?.id === message.id ? null : current));
        setEditingMessageId((current) => (current === message.id ? null : current));
        if (editingMessageId === message.id) {
          setEditingDraft("");
        }
      }
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
    if (tokenPair === null || newSpaceName.trim() === "") {
      return;
    }
    setError(null);
    setBusyAction("create-group");
    try {
      const room = await createGroupConversation(tokenPair.access_token, newSpaceName.trim());
      await refreshConversations(tokenPair.access_token);
      setSelectedRoomId(room.id);
      setNewSpaceName("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create group.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleStartDirectMessage(emailOverride?: string) {
    const emailToAdd = (emailOverride ?? contactEmail).trim();
    if (tokenPair === null || emailToAdd === "") {
      return;
    }
    if (emailToAdd.toLowerCase() === tokenPair.user.email.toLowerCase()) {
      setError("You cannot add yourself as a friend.");
      return;
    }
    setError(null);
    setBusyAction("add-contact");
    try {
      await addFriend(tokenPair.access_token, emailToAdd);
      const room = await startGlobalDirectConversation(
        tokenPair.access_token,
        emailToAdd,
      );
      await refreshFriends(tokenPair.access_token);
      await refreshConversations(tokenPair.access_token);
      setSelectedRoomId(room.id);
      setContactEmail("");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to start direct message.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleInviteMember() {
    const emailToInvite = inviteEmail.trim();
    if (
      tokenPair === null ||
      selectedRoomId === null ||
      emailToInvite === ""
    ) {
      return;
    }
    setError(null);
    setBusyAction("invite-member");
    try {
      await inviteRoomMember(
        tokenPair.access_token,
        selectedRoomId,
        emailToInvite,
      );
      await refreshConversations(tokenPair.access_token);
      setMembers(await listRoomMembers(tokenPair.access_token, selectedRoomId));
      setInviteEmail("");
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : "Unable to invite member.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteConversation(room: Room) {
    if (tokenPair === null) {
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
      await refreshConversations(tokenPair.access_token);
    } catch (leaveError) {
      setError(leaveError instanceof Error ? leaveError.message : "Unable to delete conversation.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (
      (content === "" && attachmentDrafts.length === 0) ||
      selectedRoomId === null ||
      tokenPair === null
    ) {
      return;
    }
    setBusyAction("send");
    setError(null);
    try {
      const uploadedAttachments =
        attachmentDrafts.length === 0
          ? []
          : await uploadAttachmentDrafts(tokenPair.access_token, selectedRoomId, attachmentDrafts);
      setAttachmentDrafts([]);
      await sendMessageContent(content, {
        replyToId: replyTarget?.id ?? null,
        attachmentIds: uploadedAttachments.map((attachment) => attachment.id),
        attachmentNames: uploadedAttachments.map((attachment) => attachment.filename),
      });
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Unable to send message.");
    } finally {
      setBusyAction(null);
    }
  }

  async function sendMessageContent(content: string, options: SendMessageOptions = {}) {
    const attachmentIds = options.attachmentIds ?? [];
    if ((content === "" && attachmentIds.length === 0) || selectedRoomId === null || tokenPair === null) {
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
        attachment_ids: attachmentIds,
        attachment_names: options.attachmentNames ?? [],
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
      if (attachmentIds.length === 0 && connectionState === "connected" && clientRef.current !== null) {
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
        attachmentIds,
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

  async function uploadAttachmentDrafts(
    token: string,
    roomId: string,
    drafts: AttachmentDraft[],
  ): Promise<Attachment[]> {
    const uploadedAttachments: Attachment[] = [];
    for (const draftAttachment of drafts) {
      const intent = await createAttachmentUploadIntent(token, roomId, draftAttachment.file);
      if (intent.upload_url === null) {
        throw new Error("Attachment storage is not configured.");
      }
      await uploadAttachmentObject(intent.upload_url, draftAttachment.file);
      uploadedAttachments.push(
        await confirmAttachmentUpload(token, roomId, intent.attachment.id),
      );
    }
    return uploadedAttachments;
  }

  function handleAttachmentFiles(files: FileList | null) {
    if (files === null) {
      return;
    }
    const nextDrafts = [...files].map((file) => ({
      id: createLocalId(),
      file,
    }));
    setAttachmentDrafts((current) => [...current, ...nextDrafts].slice(0, 6));
    if (fileInputRef.current !== null) {
      fileInputRef.current.value = "";
    }
  }

  function removeAttachmentDraft(id: string) {
    setAttachmentDrafts((current) => current.filter((attachment) => attachment.id !== id));
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
    if (tokenPair === null) {
      return;
    }
    setBusyAction("refresh");
    setError(null);
    try {
      await refreshConversations(tokenPair.access_token);
      if (selectedRoomId !== null) {
        setMessages(await listMessages(tokenPair.access_token, selectedRoomId));
        setMembers(await listRoomMembers(tokenPair.access_token, selectedRoomId));
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
    const roomId = selectedRoomId;
    setBusyAction(`delete-${message.id}`);
    setError(null);
    try {
      const deletedMessage = await deleteMessage(tokenPair.access_token, roomId, message.id);
      setMessages((current) =>
        current.map((item) => (item.id === message.id ? deletedMessage : item)),
      );
      setSearchResults((current) =>
        current.map((item) => (item.id === message.id ? deletedMessage : item)),
      );
      if (replyTarget?.id === message.id) {
        setReplyTarget(null);
      }
      if (editingMessageId === message.id) {
        setEditingMessageId(null);
        setEditingDraft("");
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete message.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDownloadAttachment(attachment: Attachment) {
    if (tokenPair === null || selectedRoomId === null) {
      return;
    }
    setError(null);
    try {
      const intent = await createAttachmentDownloadIntent(
        tokenPair.access_token,
        selectedRoomId,
        attachment.id,
      );
      if (intent.download_url === null) {
        throw new Error("Attachment download URL is unavailable.");
      }
      window.open(intent.download_url, "_blank", "noopener,noreferrer");
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Unable to download attachment.");
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
    setRooms([]);
    setMembers([]);
    setFriends([]);
    setServerUsers([]);
    setMessages([]);
    setPendingMessages([]);
    setAttachmentDrafts([]);
    setNewSpaceName("");
    setContactEmail("");
    setInviteEmail("");
    setProfileName("");
    setMessageSearchQuery("");
    setSearchResults([]);
    setReplyTarget(null);
    setEditingMessageId(null);
    setEditingDraft("");
    setSelectedRoomId(null);
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

        <div className="profile-box">
          <div className="profile-avatar">
            <UserRound size={18} />
          </div>
          <div className="profile-fields">
            <span>{tokenPair.user.email}</span>
            <input
              value={profileName}
              aria-label="Display name"
              onChange={(event) => setProfileName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void handleSaveProfile();
                }
              }}
            />
          </div>
          <button
            className="icon-button"
            title="Save profile"
            disabled={
              profileName.trim() === "" ||
              profileName.trim() === tokenPair.user.display_name ||
              busyAction === "profile"
            }
            onClick={() => void handleSaveProfile()}
          >
            <Check size={16} />
          </button>
        </div>

        <div className="search-box">
          <Search size={16} />
          <input
            value={searchQuery}
            placeholder="Find people and groups"
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </div>

        <div className="sidebar-scroll">
          <nav className="sidebar-nav" aria-label="Chat sections">
            <button className={chatView === "home" ? "active" : ""} onClick={() => setChatView("home")}>
              <Home size={16} />
              <span>Home</span>
              <small>{rooms.length}</small>
            </button>
            <button
              className={chatView === "friends" ? "active" : ""}
              onClick={() => setChatView("friends")}
            >
              <UserRound size={16} />
              <span>Friends</span>
              <small>{friends.length}</small>
            </button>
            <button
              className={chatView === "groups" ? "active" : ""}
              onClick={() => setChatView("groups")}
            >
              <UsersRound size={16} />
              <span>Groups</span>
              <small>{spaceRooms.length}</small>
            </button>
          </nav>

          <section className="sidebar-group room-section">
            <div className="group-heading">
              <span>
                {chatView === "home" ? "Recent" : chatView === "friends" ? "Direct messages" : "Groups"}
              </span>
              <small>
                {chatView === "home"
                  ? visibleHomeRooms.length
                  : chatView === "friends"
                    ? visibleDirectRooms.length
                    : visibleSpaceRooms.length}
              </small>
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
                  <span>{room.name}</span>
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
            {chatView === "home" && visibleHomeRooms.length === 0 && (
              <div className="empty-list">Your recent chats will appear here.</div>
            )}
            {chatView === "friends" && directRooms.length === 0 && (
              <div className="empty-list">Add a friend to start chatting.</div>
            )}
            {chatView === "groups" && spaceRooms.length === 0 && (
              <div className="empty-list">Create a group to start collaborating.</div>
            )}
          </section>

          <section className="sidebar-group compose-section">
            <div className="group-heading">
              <span>Start</span>
            </div>
            {(chatView === "home" || chatView === "friends") && (
              <div className="new-room">
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
            )}

            {(chatView === "home" || chatView === "groups") && (
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
            )}

            {selectedRoom !== undefined && !selectedRoom.is_private && (
              <div className="new-room group-member-entry">
                <input
                  value={inviteEmail}
                  placeholder="Add member to selected group"
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
          </section>

          {(chatView === "home" || chatView === "friends") && (
            <section className="sidebar-group people-section">
              <div className="group-heading">
                <span>{chatView === "friends" ? "Friends" : "People"}</span>
                <small>{chatView === "friends" ? visibleFriends.length : visibleServerUsers.length}</small>
              </div>
              {(chatView === "friends" ? visibleFriends : visibleServerUsers).slice(0, 10).map((user) => {
                const userId = "user_id" in user ? user.user_id : user.id;
                const status = presenceByUserId.get(userId);
                return (
                  <div key={userId} className="person-entry">
                    <button
                      className="person-main"
                      title={user.email}
                      onClick={() => setContactEmail(user.email)}
                    >
                      <span className={status === undefined ? "presence-dot" : "presence-dot online"} />
                      <span>
                        <strong>{user.display_name}</strong>
                        <small>{user.email}</small>
                      </span>
                    </button>
                    <button
                      className="icon-button"
                      title="Add friend or open direct chat"
                      disabled={busyAction === "add-contact"}
                      onClick={() => void handleStartDirectMessage(user.email)}
                    >
                      <UserPlus size={16} />
                    </button>
                  </div>
                );
              })}
              {chatView === "friends" && visibleFriends.length === 0 && (
                <div className="empty-list">Add a friend to keep them here.</div>
              )}
              {chatView === "home" && visibleServerUsers.length === 0 && (
                <div className="empty-list">No users match this search.</div>
              )}
            </section>
          )}
        </div>
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
                                    attachmentIds: message.attachment_ids,
                                    attachmentNames: message.attachment_names,
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
                      {(isPending ? message.attachment_names : message.attachments).length > 0 && (
                        <div className="attachment-list">
                          {isPending
                            ? message.attachment_names.map((name) => (
                                <div key={name} className="attachment-chip">
                                  <Paperclip size={14} />
                                  <span>{name}</span>
                                </div>
                              ))
                            : message.attachments.map((attachment) =>
                                attachment.content_type.startsWith("image/") ? (
                                  <button
                                    key={attachment.id}
                                    className="image-attachment"
                                    onClick={() => void handleDownloadAttachment(attachment)}
                                  >
                                    <Paperclip size={15} />
                                    <span>{attachment.filename}</span>
                                  </button>
                                ) : (
                                  <button
                                    key={attachment.id}
                                    className="attachment-chip"
                                    onClick={() => void handleDownloadAttachment(attachment)}
                                  >
                                    <Download size={14} />
                                    <span>{attachment.filename}</span>
                                  </button>
                                ),
                              )}
                        </div>
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
            <div className="emoji-row" aria-label="Quick emoji reactions">
              <button
                type="button"
                title="Attach files"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip size={16} />
              </button>
              {QUICK_EMOJIS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  title={`Insert ${emoji}`}
                  onClick={() => setDraft((current) => `${current}${emoji}`)}
                >
                  {emoji}
                </button>
              ))}
            </div>
            <input
              ref={fileInputRef}
              className="file-input"
              type="file"
              multiple
              onChange={(event) => handleAttachmentFiles(event.target.files)}
            />
            {attachmentDrafts.length > 0 && (
              <div className="attachment-drafts">
                {attachmentDrafts.map((attachment) => (
                  <div key={attachment.id} className="attachment-chip">
                    <Paperclip size={14} />
                    <span>{attachment.file.name}</span>
                    <button title="Remove attachment" onClick={() => removeAttachmentDraft(attachment.id)}>
                      <X size={13} />
                    </button>
                  </div>
                ))}
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
              disabled={
                (draft.trim() === "" && attachmentDrafts.length === 0) ||
                selectedRoomId === null ||
                busyAction === "send"
              }
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
          {connection?.skipped.length ? (
            <div className="fallback-details">
              {connection.skipped.map((item) => (
                <div key={`${item.transport}-${item.reason}`} className="fallback-row">
                  <strong>{item.transport}</strong>
                  <span>{skippedReasonLabel(item)}</span>
                </div>
              ))}
            </div>
          ) : null}
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
  members: RoomMember[],
): string {
  if (message.sender_id === currentUser.id) {
    return currentUser.display_name || "You";
  }
  const member = members.find((item) => item.user_id === message.sender_id);
  return member?.display_name ?? "Unknown";
}

function typingLabel(userIds: string[], members: RoomMember[]): string {
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

function filterUsers(users: User[], query: string, currentUserId?: string): User[] {
  return users.filter((user) => {
    if (user.id === currentUserId) {
      return false;
    }
    if (query === "") {
      return true;
    }
    return (
      user.display_name.toLowerCase().includes(query) ||
      user.email.toLowerCase().includes(query)
    );
  });
}

function filterFriends(friends: Friend[], query: string): Friend[] {
  if (query === "") {
    return friends;
  }
  return friends.filter(
    (friend) =>
      friend.display_name.toLowerCase().includes(query) ||
      friend.email.toLowerCase().includes(query),
  );
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

function skippedReasonLabel(item: ConnectResult["skipped"][number]): string {
  if (item.reason.trim() !== "") {
    return item.reason;
  }
  if (item.status !== undefined) {
    return `Transport was skipped with server status ${item.status}.`;
  }
  return "The browser did not expose a detailed WebTransport failure reason.";
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(<App />);
