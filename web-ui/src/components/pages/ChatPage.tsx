"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Streamdown } from "streamdown";

interface Message {
  role: "user" | "assistant" | "error";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [provider, setProvider] = useState("gemini");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const ws = new WebSocket(`ws://${window.location.host}/api/chat`);

      ws.onopen = () => {
        ws.send(JSON.stringify({ message: userMessage, provider }));
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "start") {
          setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
        } else if (data.type === "response") {
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1].content = data.content;
            return newMessages;
          });
        } else if (data.type === "error") {
          setMessages((prev) => [...prev, { role: "error", content: data.content }]);
        } else if (data.type === "done") {
          setIsLoading(false);
          ws.close();
        }
      };

      ws.onerror = () => {
        setIsLoading(false);
        setMessages((prev) => [
          ...prev,
          { role: "error", content: "Connection error. Please try again." },
        ]);
      };

      ws.onclose = () => setIsLoading(false);
    } catch (error) {
      setIsLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "error", content: String(error) },
      ]);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span className="text-2xl">💬</span> Chat
        </h1>
        <p className="text-sm text-zinc-400 mt-1">Talk to your AI coding assistant</p>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 overflow-auto" style={{ height: 'calc(100vh - 180px)' }}>
        <div className="px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-20">
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ repeat: Infinity, duration: 2 }}
              className="text-6xl mb-4"
            >
              💬
            </motion.div>
            <h3 className="text-lg font-medium text-zinc-300">Start a conversation</h3>
            <p className="text-sm text-zinc-500 mt-2 max-w-md">
              Ask UnClaude to help with coding, debugging, or any development task.
            </p>
          </div>
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-3"
              >
                <div
                  className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
                    msg.role === "user"
                      ? "bg-blue-600"
                      : msg.role === "error"
                      ? "bg-red-600"
                      : "bg-gradient-to-br from-purple-600 to-blue-600"
                  }`}
                >
                  {msg.role === "user" ? (
                    <User className="w-4 h-4" />
                  ) : (
                    <Bot className="w-4 h-4" />
                  )}
                </div>
                <Card className={`flex-1 p-4 ${
                  msg.role === "user" 
                    ? "bg-zinc-800/50 border-zinc-700" 
                    : msg.role === "error"
                    ? "bg-red-950/30 border-red-900/50"
                    : "bg-zinc-900 border-zinc-800"
                }`}>
                  {msg.role === "assistant" ? (
                    <Streamdown isAnimating={isLoading && i === messages.length - 1}>
                      {msg.content || "Thinking..."}
                    </Streamdown>
                  ) : (
                    <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap">
                      {msg.content || (
                        <span className="inline-flex gap-1">
                          <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                          <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                          <span className="w-2 h-2 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                        </span>
                      )}
                    </div>
                  )}
                </Card>
              </motion.div>
            ))}
            <div ref={scrollRef} />
          </div>
        )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t border-zinc-800 bg-zinc-900/50 backdrop-blur-xl p-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-2 mb-3">
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="w-32 h-8 bg-zinc-800 border-zinc-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gemini">Gemini</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="anthropic">Anthropic</SelectItem>
                <SelectItem value="ollama">Ollama</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Textarea
              placeholder="Ask UnClaude anything..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              className="flex-1 min-h-[48px] max-h-[200px] bg-zinc-800 border-zinc-700 resize-none"
              rows={1}
            />
            <Button
              onClick={sendMessage}
              disabled={isLoading || !input.trim()}
              className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
