import { useState, useEffect, useRef } from "react";

interface Message {
  sender: "user" | "bot";
  text: string;
}

const API_URL = "http://localhost:8000/ask";

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== "application/pdf") {
      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: "❌ Please upload only PDF files." },
      ]);
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setMessages((prev) => [
      ...prev,
      { sender: "user", text: `📤 Uploading "${file.name}"...` },
    ]);

    try {
      const res = await fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { sender: "bot", text: `❌ ${data.error}` },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { sender: "bot", text: `✅ "${file.name}" uploaded successfully!` },
        ]);
      }
    } catch (error) {
      console.log("Upload error:", error);
      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: "⚠️ Upload failed. Server error." },
      ]);
    }
  };

  useEffect(scrollToBottom, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMessage: Message = { sender: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);

    setInput("");
    setLoading(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userMessage.text }),
      });

      const data = await res.json();
      const botMessage: Message = {
        sender: "bot",
        text: data.answer || "No response",
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      console.log("Error:", error);
      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: "⚠️ Error connecting to server" },
      ]);
    }

    setLoading(false);
  };

  const handleKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
  };

  return (
    <div className="h-screen w-full bg-gray-100 flex flex-col items-center py-6 px-3">
      <div className="w-full max-w-3xl bg-white shadow-lg rounded-xl p-6 flex flex-col h-full">
        <h1 className="text-2xl font-bold text-center mb-4">
          🤖 RAG Chatbot (Groq + LangChain + FastAPI)
        </h1>
        <div className="mb-4">
          <label className="flex items-center gap-3 cursor-pointer bg-gray-200 hover:bg-gray-300 p-3 rounded-lg w-fit">
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => handleFileUpload(e)}
            />
            <span className="font-medium">📎 Upload PDF</span>
          </label>
        </div>
        {/* CHAT WINDOW */}
        <div className="flex-1 overflow-y-auto border rounded-lg p-4 bg-gray-50 space-y-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${
                msg.sender === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`px-4 py-2 max-w-xs rounded-xl text-white ${
                  msg.sender === "user"
                    ? "bg-blue-600 rounded-br-none"
                    : "bg-gray-700 rounded-bl-none"
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}

          {loading && (
            <div className="text-gray-500 text-sm animate-pulse">Thinking…</div>
          )}

          <div ref={chatEndRef}></div>
        </div>

        {/* INPUT BAR */}
        <div className="mt-4 flex">
          <input
            className="flex-1 border p-3 rounded-l-lg outline-none"
            type="text"
            placeholder="Ask me anything…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
          />
          <button
            className="bg-blue-600 text-white px-6 rounded-r-lg hover:bg-blue-700 transition"
            onClick={sendMessage}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
