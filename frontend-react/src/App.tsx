import React, { useEffect, useRef, useState } from "react";

interface Message {
  sender: "user" | "bot";
  text: string;
}

interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  messages: Message[];
}

const ASK_API_URL = "http://localhost:8000/ask";
const UPLOAD_API_URL = "http://localhost:8000/upload";
const THEME_KEY = "rag-theme";

const App: React.FC = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isDark, setIsDark] = useState(true);
  const [uploading, setUploading] = useState(false);

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
      // fallback: prefer system dark
      const prefersDark = window.matchMedia?.(
        "(prefers-color-scheme: dark)"
      ).matches;
      setIsDark(prefersDark);
    }
  }, []);

  // Persist theme
  useEffect(() => {
    localStorage.setItem(THEME_KEY, isDark ? "dark" : "light");
  }, [isDark]);

  // ---- Initial conversation ----
  useEffect(() => {
    if (conversations.length === 0) {
      const first: Conversation = {
        id: crypto.randomUUID(),
        title: "New chat",
        createdAt: Date.now(),
        messages: [],
      };
      setConversations([first]);
      setActiveId(first.id);
    }
  }, [conversations.length]);

  const activeConversation =
    conversations.find((c) => c.id === activeId) || conversations[0];
  const messages = activeConversation?.messages ?? [];

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, loading]);

  // ---- Helpers for conversation updates ----
  const updateConversationMessages = (
    convId: string,
    updater: (msgs: Message[]) => Message[]
  ) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId ? { ...c, messages: updater(c.messages) } : c
      )
    );
  };

  const addMessageToActive = (msg: Message) => {
    if (!activeConversation) return;
    updateConversationMessages(activeConversation.id, (msgs) => [...msgs, msg]);
  };

  const renameConversationIfNeeded = (
    convId: string,
    firstUserMessage: string
  ) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId && c.title === "New chat"
          ? {
              ...c,
              title:
                firstUserMessage.slice(0, 40) +
                (firstUserMessage.length > 40 ? "…" : ""),
            }
          : c
      )
    );
  };

  // ---- Send message ----
  const sendMessage = async () => {
    if (!input.trim() || loading || !activeConversation) return;

    const text = input.trim();
    setInput("");

    const userMsg: Message = { sender: "user", text };
    addMessageToActive(userMsg);
    renameConversationIfNeeded(activeConversation.id, text);
    setLoading(true);

    try {
      const res = await fetch(ASK_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });

      const data = await res.json();
      const botMsg: Message = {
        sender: "bot",
        text: data.answer || "No response from server.",
      };

      addMessageToActive(botMsg);
    } catch (error) {
      console.error("Error connecting to server:", error);
      addMessageToActive({
        sender: "bot",
        text: "⚠️ Error connecting to server.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
  };

  // ---- Clear chat (only active conversation) ----
  const clearChat = () => {
    if (!activeConversation) return;
    updateConversationMessages(activeConversation.id, () => []);
  };

  // ---- New conversation ----
  const createNewConversation = () => {
    const conv: Conversation = {
      id: crypto.randomUUID(),
      title: "New chat",
      createdAt: Date.now(),
      messages: [],
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

  // ---- File upload ----
  const handleFileUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeConversation) return;

    if (file.type !== "application/pdf") {
      addMessageToActive({
        sender: "bot",
        text: "❌ Please upload only PDF files.",
      });
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    addMessageToActive({
      sender: "user",
      text: `📤 Uploading "${file.name}"…`,
    });

    setUploading(true);
    try {
      const res = await fetch(UPLOAD_API_URL, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.error) {
        addMessageToActive({
          sender: "bot",
          text: `❌ Upload failed: ${data.error}`,
        });
      } else {
        addMessageToActive({
          sender: "bot",
          text: `✅ "${file.name}" uploaded and processed. You can now ask questions about it.`,
        });
      }
    } catch (error) {
      console.error("Upload error:", error);
      addMessageToActive({
        sender: "bot",
        text: "⚠️ Upload failed. Server error.",
      });
    } finally {
      setUploading(false);
      // reset input so same file can be re-selected if needed
      if (fileInputRef.current) fileInputRef.current.value = "";
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
      className={`${containerBg} min-h-screen flex items-center justify-center py-6 px-3`}
    >
      <div
        className={`${shellBg} w-full max-w-6xl rounded-3xl shadow-2xl border border-white/10 p-2 md:p-3 transition-transform duration-300 hover:scale-[1.01]`}
      >
        <div
          className={`rounded-3xl flex h-[80vh] md:h-[82vh] overflow-hidden ${
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
                className="text-xs px-2 py-1 rounded-full bg-emerald-500 text-white hover:bg-emerald-400 transition"
              >
                + New
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {conversations.map((conv) => {
                const isActive = conv.id === activeConversation?.id;
                return (
                  <button
                    key={conv.id}
                    type="button"
                    onClick={() => switchConversation(conv.id)}
                    className={`w-full text-left px-4 py-3 text-xs border-b border-slate-800/30 flex flex-col gap-0.5 transition ${
                      isActive
                        ? isDark
                          ? "bg-slate-800 text-slate-50"
                          : "bg-slate-200 text-slate-900"
                        : isDark
                        ? "hover:bg-slate-900 text-slate-300"
                        : "hover:bg-slate-100 text-slate-700"
                    }`}
                  >
                    <span className="font-medium truncate">{conv.title}</span>
                    <span className="text-[10px] opacity-70">
                      {conv.messages.length} message
                      {conv.messages.length === 1 ? "" : "s"}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="p-3 text-[10px] opacity-60">
              <div>RAG ChatApp</div>
              <div>Groq · LangChain · Chroma</div>
            </div>
          </aside>

          {/* Main Chat Area */}
          <main className="flex-1 flex flex-col p-4 md:p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-3 md:mb-4 gap-3">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h1 className="text-lg md:text-2xl font-bold flex items-center gap-2">
                    <span>🤖 RAG Chatbot</span>
                  </h1>
                  <span className="hidden sm:inline text-[10px] md:text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    Groq · LangChain · Chroma
                  </span>
                </div>
                <p className="text-[11px] md:text-xs opacity-70">
                  Ask questions about your uploaded PDFs. Only relevant chunks
                  are sent to the LLM.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {/* Upload button */}
                <button
                  type="button"
                  onClick={handleFileUploadClick}
                  disabled={uploading}
                  className={`text-xs md:text-sm px-3 py-1.5 rounded-full flex items-center gap-1 border transition ${
                    uploading
                      ? "border-slate-500/40 text-slate-400 cursor-wait"
                      : isDark
                      ? "border-slate-600 text-slate-100 hover:bg-slate-800/80"
                      : "border-slate-300 text-slate-800 hover:bg-slate-100"
                  }`}
                >
                  <span>📎</span>
                  <span>{uploading ? "Uploading…" : "Upload PDF"}</span>
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  accept="application/pdf"
                  onChange={handleFileChange}
                />

                {/* Clear chat */}
                <button
                  type="button"
                  onClick={clearChat}
                  className="hidden sm:inline-flex text-xs md:text-sm px-3 py-1.5 rounded-full border border-red-500/40 text-red-400 hover:bg-red-500/10 transition"
                  disabled={!messages.length}
                >
                  🧹 Clear
                </button>

                {/* Theme toggle */}
                <button
                  type="button"
                  onClick={() => setIsDark((prev) => !prev)}
                  className={`w-9 h-9 flex items-center justify-center rounded-full border transition ${
                    isDark
                      ? "border-slate-600 bg-slate-900 text-yellow-300 hover:border-slate-300"
                      : "border-slate-300 bg-white text-yellow-500 hover:border-slate-500"
                  }`}
                >
                  {isDark ? "🌙" : "☀️"}
                </button>
              </div>
            </div>

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
                  className={`text-xs md:text-sm opacity-70 text-center mt-10 ${
                    isDark ? "text-slate-300" : "text-slate-500"
                  }`}
                >
                  👋 Start by uploading a PDF or asking a question like{" "}
                  <span className="italic">
                    &ldquo;Summarize the main points of the latest
                    document.&rdquo;
                  </span>
                </div>
              )}

              {messages.map((msg, i) => {
                const isUser = msg.sender === "user";
                return (
                  <div
                    key={i}
                    className={`flex w-full ${
                      isUser ? "justify-end" : "justify-start"
                    } animate-[fadeIn_0.25s_ease-out]`}
                  >
                    <div
                      className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm md:text-[15px] shadow-sm transition-transform duration-200 hover:-translate-y-[1px] ${
                        isUser
                          ? isDark
                            ? "bg-blue-600 text-white rounded-br-sm"
                            : "bg-blue-500 text-white rounded-br-sm"
                          : isDark
                          ? "bg-slate-800 text-slate-100 rounded-bl-sm"
                          : "bg-white text-slate-900 rounded-bl-sm border border-slate-200"
                      }`}
                    >
                      {msg.text}
                    </div>
                  </div>
                );
              })}

              {loading && (
                <div className="flex justify-start mt-2">
                  <div
                    className={`px-4 py-2 rounded-2xl text-xs md:text-sm border border-dashed flex items-center gap-2 ${
                      isDark
                        ? "border-slate-600 text-slate-300"
                        : "border-slate-300 text-slate-600"
                    }`}
                  >
                    <span>Thinking</span>
                    <span className="typing-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </span>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>

            {/* Input Bar */}
            <div className="mt-4 flex gap-2 items-center">
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
              <button
                type="button"
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className={`px-4 md:px-5 py-2.5 rounded-2xl text-sm md:text-[15px] font-medium flex items-center gap-1 transition
                ${
                  loading || !input.trim()
                    ? "bg-slate-400/40 text-slate-200 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-500/25"
                }`}
              >
                <span>Send</span> <span>➤</span>
              </button>
            </div>

            {/* Mobile clear button */}
            {messages.length > 0 && (
              <button
                type="button"
                onClick={clearChat}
                className="mt-2 text-[11px] text-center text-red-400 hover:text-red-300 underline sm:hidden"
              >
                Clear chat
              </button>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default App;
