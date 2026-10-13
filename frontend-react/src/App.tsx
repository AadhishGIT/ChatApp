import React, { useEffect, useMemo, useRef, useState } from "react";

interface Message {
  sender: "user" | "bot";
  text: string;
  visualization?: Visualization;
  sources?: Array<Record<string, unknown>>;
}

interface Visualization {
  kind: "bar";
  title: string;
  labels: string[];
  values: number[];
  summary: string;
}

interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  messages: Message[];
  pdfs: string[];
}

interface BackendInfo {
  status: string;
  llmConfigured: boolean;
  supabaseConfigured: boolean;
  vectorStore: string;
  model?: string;
}

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const ASK_API_URL = `${API_BASE_URL}/ask`;
const ASK_STREAM_URL = `${API_BASE_URL}/ask/stream`;
const UPLOAD_API_URL = `${API_BASE_URL}/upload`;
const RESET_API_URL = `${API_BASE_URL}/reset`;
const HEALTH_API_URL = `${API_BASE_URL}/health`;
const THEME_KEY = "rag-theme";
const SESSIONS_STORAGE_KEY = "documind-conversations-v2";

const errorMessage = async (response: Response) => {
  const payload = await response.json().catch(() => null);
  return (
    payload?.detail ||
    payload?.error ||
    `Server returned status ${response.status}`
  );
};

const App: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>(() => {
    try {
      const saved = localStorage.getItem(SESSIONS_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // fallback
    }
    const defaultConv: Conversation = {
      id: crypto.randomUUID(),
      title: "New chat",
      createdAt: Date.now(),
      messages: [],
      pdfs: [],
    };
    return [defaultConv];
  });

  const [activeId, setActiveId] = useState<string | null>(() => {
    return conversations[0]?.id ?? null;
  });

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isDark, setIsDark] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [serverStatus, setServerStatus] = useState<
    "checking" | "ready" | "waking_up" | "error"
  >("checking");
  const [backendInfo, setBackendInfo] = useState<BackendInfo | null>(null);

  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ---- Setup: dark mode from localStorage ----
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light") {
      setIsDark(false);
    } else if (saved === "dark") {
      setIsDark(true);
    } else {
      const prefersDark = window.matchMedia?.(
        "(prefers-color-scheme: dark)",
      ).matches;
      setIsDark(prefersDark ?? true);
    }
  }, []);

  // Persist theme
  useEffect(() => {
    localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
  }, [isDark]);

  // Persist conversations
  useEffect(() => {
    try {
      localStorage.setItem(
        SESSIONS_STORAGE_KEY,
        JSON.stringify(conversations),
      );
    } catch {
      // ignore storage quota errors
    }
  }, [conversations]);

  // ---- Health & Cold-Start Checker ----
  const checkHealth = async () => {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 6000);
      const res = await fetch(HEALTH_API_URL, { signal: controller.signal });
      clearTimeout(timer);
      if (res.ok) {
        const data: BackendInfo = await res.json();
        setBackendInfo(data);
        setServerStatus("ready");
        return true;
      }
      setServerStatus("waking_up");
      return false;
    } catch {
      setServerStatus("waking_up");
      return false;
    }
  };

  useEffect(() => {
    checkHealth();
    // Periodically poll if server is waking up
    const interval = setInterval(() => {
      if (serverStatus !== "ready") {
        checkHealth();
      }
    }, 8000);
    return () => clearInterval(interval);
  }, [serverStatus]);

  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? conversations[0],
    [conversations, activeId],
  );

  const messages = useMemo(
    () => activeConversation?.messages ?? [],
    [activeConversation],
  );

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // ---- Helpers ----
  const updateConversation = (
    convId: string,
    updater: (c: Conversation) => Conversation,
  ) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? updater(c) : c)),
    );
  };

  const updateConversationMessages = (
    convId: string,
    updater: (msgs: Message[]) => Message[],
  ) => {
    updateConversation(convId, (c) => ({
      ...c,
      messages: updater(c.messages),
    }));
  };

  const addMessageToActive = (msg: Message) => {
    if (!activeConversation) return;
    updateConversationMessages(activeConversation.id, (msgs) => [...msgs, msg]);
  };

  const updateLastMessage = (text: string, sources?: Array<Record<string, unknown>>) => {
    if (!activeConversation) return;
    updateConversationMessages(activeConversation.id, (msgs) => {
      if (msgs.length === 0) return msgs;
      const lastIndex = msgs.length - 1;
      const updated = [...msgs];
      updated[lastIndex] = {
        ...updated[lastIndex],
        text,
        ...(sources ? { sources } : {}),
      };
      return updated;
    });
  };

  const renameConversationIfNeeded = (
    convId: string,
    firstUserMessage: string,
  ) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId && c.title === "New chat"
          ? {
              ...c,
              title:
                firstUserMessage.slice(0, 36) +
                (firstUserMessage.length > 36 ? "…" : ""),
            }
          : c,
      ),
    );
  };

  const addPdfToActive = (fileName: string) => {
    if (!activeConversation) return;
    updateConversation(activeConversation.id, (c) => {
      if (c.pdfs.includes(fileName)) return c;
      return { ...c, pdfs: [...c.pdfs, fileName] };
    });
  };

  const removePdfFromActive = async (fileName: string) => {
    if (!activeConversation) return;
    updateConversation(activeConversation.id, (c) => ({
      ...c,
      pdfs: c.pdfs.filter((n) => n !== fileName),
    }));

    // Also trigger deletion on backend if user confirms
    try {
      await fetch(
        `${API_BASE_URL}/documents/${encodeURIComponent(fileName)}?session_id=${activeConversation.id}`,
        { method: "DELETE" },
      );
    } catch {
      // Best-effort removal
    }
  };

  // ---- Streaming Message Handler with SSE ----
  const sendMessage = async () => {
    if (!input.trim() || loading || !activeConversation) return;

    const text = input.trim();
    setInput("");

    const userMsg: Message = { sender: "user", text };
    addMessageToActive(userMsg);
    renameConversationIfNeeded(activeConversation.id, text);
    setLoading(true);

    // Initial placeholder for bot message
    const botPlaceholder: Message = { sender: "bot", text: "" };
    addMessageToActive(botPlaceholder);

    let streamSucceeded = false;
    let accumulatedText = "";

    try {
      // Attempt SSE streaming first
      const res = await fetch(ASK_STREAM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          sources: activeConversation.pdfs,
          session_id: activeConversation.id,
        }),
      });

      if (res.ok && res.body) {
        streamSucceeded = true;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const trimmed = part.trim();
            if (trimmed.startsWith("data: ")) {
              try {
                const parsed = JSON.parse(trimmed.slice(6));
                if (parsed.type === "token" && parsed.token) {
                  accumulatedText += parsed.token;
                  updateLastMessage(accumulatedText);
                } else if (parsed.type === "error") {
                  accumulatedText = `⚠️ ${parsed.text || "Error answering query."}`;
                  updateLastMessage(accumulatedText);
                } else if (parsed.type === "done" && parsed.sources) {
                  updateLastMessage(accumulatedText, parsed.sources);
                }
              } catch {
                // ignore SSE parse errors
              }
            }
          }
        }
      }
    } catch {
      streamSucceeded = false;
    }

    // Fallback to standard /ask if streaming wasn't supported
    if (!streamSucceeded || !accumulatedText.trim()) {
      try {
        const res = await fetch(ASK_API_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: text,
            sources: activeConversation.pdfs,
            session_id: activeConversation.id,
          }),
        });

        if (!res.ok) {
          throw new Error(await errorMessage(res));
        }

        const data = await res.json();
        updateConversationMessages(activeConversation.id, (msgs) => {
          const updated = [...msgs];
          updated[updated.length - 1] = {
            sender: "bot",
            text: data.answer || "No response received.",
            visualization: data.visualization ?? undefined,
            sources: data.sources ?? undefined,
          };
          return updated;
        });
      } catch (fallbackError) {
        updateLastMessage(
          `⚠️ ${fallbackError instanceof Error ? fallbackError.message : "Error connecting to backend."}`,
        );
      }
    }

    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
  };

  // ---- Clear chat ----
  const clearChat = () => {
    if (!activeConversation) return;
    updateConversationMessages(activeConversation.id, () => []);
  };

  // ---- Export chat as Markdown ----
  const exportChat = () => {
    if (!activeConversation || activeConversation.messages.length === 0) return;
    const content = [
      `# ${activeConversation.title}`,
      `*Date: ${new Date(activeConversation.createdAt).toLocaleString()}*`,
      activeConversation.pdfs.length > 0
        ? `*Sources: ${activeConversation.pdfs.join(", ")}*`
        : "",
      "---",
      "",
      ...activeConversation.messages.map((m) =>
        m.sender === "user"
          ? `### 👤 You\n${m.text}\n`
          : `### 🤖 DocuMind\n${m.text}\n`,
      ),
    ].join("\n");

    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${activeConversation.title.replace(/[^a-zA-Z0-9_-]/g, "_")}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // ---- New conversation ----
  const createNewConversation = () => {
    const conv: Conversation = {
      id: crypto.randomUUID(),
      title: "New chat",
      createdAt: Date.now(),
      messages: [],
      pdfs: [],
    };
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    setInput("");
  };

  // ---- Switch conversation ----
  const switchConversation = (id: string) => {
    setActiveId(id);
    setInput("");
  };

  // ---- Delete conversation ----
  const deleteConversation = (id: string) => {
    setConversations((prev) => {
      const filtered = prev.filter((c) => c.id !== id);
      if (filtered.length === 0) {
        const newConv: Conversation = {
          id: crypto.randomUUID(),
          title: "New chat",
          createdAt: Date.now(),
          messages: [],
          pdfs: [],
        };
        setActiveId(newConv.id);
        return [newConv];
      } else {
        if (activeId === id) {
          setActiveId(filtered[0].id);
        }
        return filtered;
      }
    });
  };

  // ---- File upload ----
  const handleFileUploadClick = () => {
    if (uploading) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeConversation) return;

    if (
      file.type !== "application/pdf" &&
      !file.name.toLowerCase().endsWith(".pdf")
    ) {
      addMessageToActive({
        sender: "bot",
        text: "❌ Please upload only PDF files.",
      });
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      addMessageToActive({
        sender: "bot",
        text: `❌ File exceeds the free tier 25 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB). Please select a PDF under 25 MB.`,
      });
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", activeConversation.id);

    addMessageToActive({
      sender: "user",
      text: `📤 Uploading "${file.name}" (${(file.size / 1024).toFixed(0)} KB)…`,
    });

    setUploading(true);
    try {
      const res = await fetch(UPLOAD_API_URL, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        throw new Error(await errorMessage(res));
      }
      const data = await res.json();
      addMessageToActive({
        sender: "bot",
        text: `✅ "${data.filename ?? file.name}" indexed successfully into Supabase (${data.chunks ?? 1} chunks). Ask any questions!`,
      });
      addPdfToActive(data.filename ?? file.name);
    } catch (error) {
      const errStr = error instanceof Error ? error.message : "Server error.";
      const isQuota =
        errStr.includes("429") ||
        errStr.includes("RESOURCE_EXHAUSTED") ||
        errStr.toLowerCase().includes("quota");

      if (isQuota) {
        addMessageToActive({
          sender: "bot",
          text: `⏳ Google AI Studio Free Tier rate limit reached (15 RPM burst limit).\n\n💡 Recommendations:\n• Please wait 30–60 seconds for the temporary burst limit to reset, then retry.\n• Recommended length: PDFs under 25–30 pages upload fastest on the free tier.\n• Click "Limits" in the top bar to inspect full free-tier parameters.`,
        });
      } else {
        addMessageToActive({
          sender: "bot",
          text: `⚠️ Upload failed: ${errStr}`,
        });
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // ---- Reset session documents ----
  const resetSessionBackend = async () => {
    if (!activeConversation) return;
    if (
      !window.confirm(
        `Reset all uploaded PDFs and indexed vectors for "${activeConversation.title}"?`,
      )
    )
      return;

    setResetting(true);
    try {
      const res = await fetch(
        `${RESET_API_URL}?session_id=${activeConversation.id}`,
        { method: "DELETE" },
      );
      if (!res.ok) {
        throw new Error(await errorMessage(res));
      }
      const data = await res.json();

      addMessageToActive({
        sender: "bot",
        text:
          data.message ||
          "🗑 Vector index for this session has been reset.",
      });

      updateConversation(activeConversation.id, (c) => ({ ...c, pdfs: [] }));
    } catch (error) {
      addMessageToActive({
        sender: "bot",
        text: `⚠️ Failed to reset: ${error instanceof Error ? error.message : "Server error."}`,
      });
    } finally {
      setResetting(false);
    }
  };

  const containerBg = isDark
    ? "bg-slate-950 text-slate-100"
    : "bg-slate-100 text-slate-900";

  const shellBg = isDark
    ? "bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950"
    : "bg-gradient-to-br from-sky-100 via-slate-50 to-slate-100";

  return (
    <div
      className={`${containerBg} min-h-screen flex flex-col items-center justify-center py-4 px-2 md:px-4`}
    >
      {/* Cold-Start / Free-tier server notice */}
      {serverStatus === "waking_up" && (
        <div className="w-full max-w-6xl mb-2 px-4 py-2.5 rounded-2xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs md:text-sm flex items-center justify-between animate-pulse">
          <div className="flex items-center gap-2">
            <span>⚡</span>
            <span>
              <strong>Connecting to free backend...</strong> Free cloud services
              (Render/Koyeb) sleep after 15 min of inactivity. Waking up takes
              ~30-40 seconds.
            </span>
          </div>
          <button
            type="button"
            onClick={checkHealth}
            className="underline hover:text-amber-200 ml-2 text-xs"
          >
            Retry Now
          </button>
        </div>
      )}

      <div
        className={`${shellBg} w-full max-w-6xl rounded-3xl shadow-2xl border border-white/10 p-2 md:p-3 transition-transform duration-300 hover:scale-[1.005]`}
      >
        <div
          className={`rounded-3xl flex h-[82vh] md:h-[84vh] overflow-hidden ${
            isDark ? "bg-slate-900/90" : "bg-white/90"
          } backdrop-blur`}
        >
          {/* Sidebar: conversations */}
          <aside
            className={`hidden md:flex md:w-64 flex-col border-r ${
              isDark
                ? "border-slate-800 bg-slate-950/40"
                : "border-slate-200 bg-slate-50"
            }`}
          >
            <div className="p-4 flex items-center justify-between border-b border-slate-700/40">
              <span className="font-semibold text-sm flex items-center gap-2">
                🧵 Sessions
              </span>
              <button
                type="button"
                onClick={createNewConversation}
                className="text-xs px-2.5 py-1 rounded-full bg-emerald-500 text-white hover:bg-emerald-400 font-medium transition"
              >
                + New
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {conversations.map((conv) => {
                const isActive = conv.id === activeConversation?.id;
                return (
                  <div
                    key={conv.id}
                    className={`flex items-center justify-between px-3 py-2.5 text-xs border-b border-slate-800/30 transition ${
                      isActive
                        ? isDark
                          ? "bg-slate-800 text-slate-50"
                          : "bg-slate-200 text-slate-900"
                        : isDark
                          ? "hover:bg-slate-900 text-slate-300"
                          : "hover:bg-slate-100 text-slate-700"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => switchConversation(conv.id)}
                      className="flex-1 text-left"
                    >
                      <div className="font-medium truncate">{conv.title}</div>
                      <div className="text-[10px] opacity-70 flex gap-2">
                        <span>
                          {conv.messages.length} msg
                          {conv.messages.length === 1 ? "" : "s"}
                        </span>
                        {conv.pdfs.length > 0 && (
                          <span>· {conv.pdfs.length} PDF</span>
                        )}
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteConversation(conv.id);
                      }}
                      className="ml-2 text-[12px] opacity-60 hover:opacity-100 text-red-400"
                      title="Delete chat"
                    >
                      🗑
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Production Stack Badge */}
            <div className="p-3 text-[10px] opacity-70 border-t border-slate-800/40 space-y-1">
              <div className="font-semibold text-slate-300">
                DocuMind Production
              </div>
              <div className="flex items-center gap-1.5 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>
                  {backendInfo?.supabaseConfigured
                    ? "Supabase pgvector"
                    : "Gemini 2.5 + Cloud"}
                </span>
              </div>
              <div className="opacity-60 text-[9px]">
                100% Free Tier · Vercel + Render
              </div>
            </div>
          </aside>

          {/* Main Chat Area */}
          <main className="flex-1 flex flex-col p-3 md:p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-3 md:mb-4 gap-2">
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <h1 className="text-lg md:text-2xl font-bold flex items-center gap-2">
                    <span>🤖 DocuMind</span>
                  </h1>
                  <span className="hidden sm:inline text-[10px] md:text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    FastAPI · Supabase · Gemini
                  </span>
                </div>
                <p className="text-[11px] md:text-xs opacity-70">
                  RAG chatbot powered by Supabase pgvector and Gemini Flash
                </p>
              </div>

              <div className="flex items-center gap-1.5 md:gap-2">
                {/* Export chat button */}
                <button
                  type="button"
                  onClick={exportChat}
                  disabled={messages.length === 0}
                  className="hidden sm:inline-flex text-xs px-3 py-1.5 rounded-full border border-slate-600/60 hover:bg-slate-800/40 transition disabled:opacity-40"
                  title="Export conversation to Markdown"
                >
                  📥 Export
                </button>

                {/* Reset PDF sources */}
                <button
                  type="button"
                  onClick={resetSessionBackend}
                  disabled={resetting}
                  className={`hidden sm:inline-flex text-xs px-3 py-1.5 rounded-full border items-center gap-1 transition ${
                    resetting
                      ? "border-amber-500/40 text-amber-300 cursor-wait"
                      : "border-amber-500/40 text-amber-300 hover:bg-amber-500/10"
                  }`}
                  title="Reset documents for this chat"
                >
                  🗑 Reset PDFs
                </button>

                {/* Clear chat */}
                <button
                  type="button"
                  onClick={clearChat}
                  className="hidden sm:inline-flex text-xs px-3 py-1.5 rounded-full border border-red-500/40 text-red-400 hover:bg-red-500/10 transition"
                  disabled={!messages.length}
                >
                  🧹 Clear
                </button>

                {/* Theme toggle */}
                <button
                  type="button"
                  onClick={() => setIsDark((prev) => !prev)}
                  className={`w-8 h-8 md:w-9 md:h-9 flex items-center justify-center rounded-full border transition ${
                    isDark
                      ? "border-slate-600 bg-slate-900 text-yellow-300 hover:border-slate-300"
                      : "border-slate-300 bg-white text-yellow-500 hover:border-slate-500"
                  }`}
                  title="Toggle theme"
                >
                  {isDark ? "🌙" : "☀️"}
                </button>
              </div>
            </div>

            {/* Attached PDFs for this chat */}
            {activeConversation?.pdfs?.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] md:text-xs">
                <span className="opacity-70">Attached Sources:</span>
                {activeConversation.pdfs.map((name) => (
                  <span
                    key={name}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs max-w-[200px] md:max-w-[260px] truncate ${
                      isDark
                        ? "border-slate-600 bg-slate-900/80 text-slate-100"
                        : "border-slate-300 bg-white text-slate-800"
                    }`}
                    title={name}
                  >
                    <span className="truncate">📄 {name}</span>
                    <button
                      type="button"
                      className="ml-1 text-[11px] opacity-60 hover:opacity-100 hover:text-red-400"
                      onClick={() => removePdfFromActive(name)}
                      title="Remove PDF"
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Chat Window */}
            <div
              className={`flex-1 overflow-y-auto rounded-2xl border p-3 md:p-4 space-y-3 ${
                isDark
                  ? "border-slate-800 bg-slate-900/70"
                  : "border-slate-200 bg-slate-50"
              }`}
            >
              {messages.length === 0 && !loading && (
                <div
                  className={`text-xs md:text-sm opacity-70 text-center mt-12 space-y-2 ${
                    isDark ? "text-slate-300" : "text-slate-500"
                  }`}
                >
                  <p className="font-medium text-base">
                    👋 Welcome to DocuMind Production
                  </p>
                  <p>
                    Attach a PDF with the paperclip button below, or ask questions
                    grounded in your knowledge base.
                  </p>
                </div>
              )}

              {messages.map((msg, i) => {
                const isUser = msg.sender === "user";
                const maximum = Math.max(...(msg.visualization?.values ?? [1]));
                return (
                  <div
                    key={i}
                    className={`flex w-full ${
                      isUser ? "justify-end" : "justify-start"
                    } animate-[fadeIn_0.25s_ease-out]`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm md:text-[15px] shadow-sm leading-relaxed ${
                        isUser
                          ? isDark
                            ? "bg-blue-600 text-white rounded-br-sm"
                            : "bg-blue-500 text-white rounded-br-sm"
                          : isDark
                            ? "bg-slate-800 text-slate-100 rounded-bl-sm border border-slate-700/50"
                            : "bg-white text-slate-900 rounded-bl-sm border border-slate-200"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{msg.text}</div>

                      {/* Visualizations */}
                      {!isUser && msg.visualization && (
                        <div
                          className={`mt-3 rounded-xl border p-3 ${
                            isDark
                              ? "border-slate-600 bg-slate-900/60"
                              : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          <div className="mb-2 font-semibold text-xs">
                            {msg.visualization.title}
                          </div>
                          <div className="space-y-2">
                            {msg.visualization.labels.map(
                              (label, chartIndex) => {
                                const value =
                                  msg.visualization?.values[chartIndex] ?? 0;
                                return (
                                  <div
                                    key={`${label}-${chartIndex}`}
                                    className="text-xs"
                                  >
                                    <div className="mb-1 flex justify-between gap-3">
                                      <span className="truncate">{label}</span>
                                      <span>{value.toLocaleString()}</span>
                                    </div>
                                    <div
                                      className={`h-2 overflow-hidden rounded-full ${
                                        isDark ? "bg-slate-700" : "bg-slate-200"
                                      }`}
                                    >
                                      <div
                                        className="h-full rounded-full bg-emerald-500"
                                        style={{
                                          width: `${Math.max(
                                            0,
                                            Math.min(
                                              100,
                                              (value / maximum) * 100,
                                            ),
                                          )}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                );
                              },
                            )}
                          </div>
                          {msg.visualization.summary && (
                            <p className="mt-3 text-xs opacity-75">
                              {msg.visualization.summary}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Sources citation footer */}
                      {!isUser && msg.sources && msg.sources.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-700/40 text-[11px] opacity-75 flex flex-wrap gap-2 items-center">
                          <span className="font-medium">Sources cited:</span>
                          {msg.sources.slice(0, 3).map((src, idx) => (
                            <span
                              key={idx}
                              className="px-1.5 py-0.5 rounded bg-black/20 text-[10px]"
                            >
                              📄 {String(src.source_name || src.source || "PDF")}{" "}
                              {src.page ? `(p. ${src.page})` : ""}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {loading && messages[messages.length - 1]?.text === "" && (
                <div className="flex justify-start mt-2">
                  <div
                    className={`px-4 py-2 rounded-2xl text-xs md:text-sm border border-dashed flex items-center gap-2 ${
                      isDark
                        ? "border-slate-600 text-slate-300"
                        : "border-slate-300 text-slate-600"
                    }`}
                  >
                    <span>Generating answer</span>
                    <span className="animate-pulse">...</span>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input Bar */}
            <div className="mt-3 md:mt-4 flex gap-2 items-center">
              {/* Upload button */}
              <button
                type="button"
                onClick={handleFileUploadClick}
                disabled={uploading}
                className={`w-10 h-10 rounded-full flex items-center justify-center border text-lg transition
                  ${
                    uploading
                      ? "border-slate-500/40 text-slate-400 cursor-wait animate-spin"
                      : isDark
                        ? "border-slate-600 text-slate-100 hover:bg-slate-800/80"
                        : "border-slate-300 text-slate-700 hover:bg-slate-100"
                  }`}
                title="Upload & index PDF"
              >
                📎
              </button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept="application/pdf"
                onChange={handleFileChange}
              />

              {/* Text input */}
              <input
                className={`flex-1 rounded-2xl px-4 py-2.5 text-sm md:text-[15px] outline-none border transition ${
                  isDark
                    ? "bg-slate-900/80 border-slate-700 text-slate-100 placeholder:text-slate-500 focus:border-blue-500"
                    : "bg-white border-slate-300 text-slate-900 placeholder:text-slate-400 focus:border-blue-500"
                }`}
                type="text"
                placeholder="Ask me anything about your PDFs..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
              />

              {/* Send button */}
              <button
                type="button"
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className={`px-4 md:px-5 py-2.5 rounded-2xl text-sm md:text-[15px] font-medium flex items-center gap-1.5 transition
                ${
                  loading || !input.trim()
                    ? "bg-slate-400/40 text-slate-200 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-500/25"
                }`}
              >
                <span>Send</span> <span>➤</span>
              </button>
            </div>

            {/* Input hint with quota details link */}
            <div className="mt-1.5 px-1 hidden sm:flex justify-between items-center text-[10px] opacity-60">
              <span>📎 Max PDF: 25 MB · Recommended: &lt; 25 pages per document</span>
            </div>

            {/* Mobile Actions */}
            <div className="mt-2 flex justify-between items-center text-[11px] sm:hidden px-1">
              <button
                type="button"
                onClick={createNewConversation}
                className="text-emerald-400 underline"
              >
                + New chat
              </button>
              {messages.length > 0 && (
                <button
                  type="button"
                  onClick={clearChat}
                  className="text-red-400 underline"
                >
                  Clear messages
                </button>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
};

export default App;
