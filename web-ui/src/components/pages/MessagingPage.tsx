"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  MessageSquare,
  Send,
  CheckCircle2,
  RefreshCw,
  Trash2,
  Eye,
  EyeOff,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

// ── Types ──────────────────────────────────────────────

interface PlatformStatus {
  configured: boolean;
  registered_chats: number;
}

interface MessagingStatus {
  platforms: Record<string, PlatformStatus>;
}

// ── Platform Card ──────────────────────────────────────

interface PlatformConfig {
  id: string;
  name: string;
  icon: string;
  color: string;
  description: string;
  fields: {
    key: string;
    label: string;
    placeholder: string;
    secret?: boolean;
  }[];
  docs_url: string;
  setup_steps: string[];
}

const PLATFORMS: PlatformConfig[] = [
  {
    id: "telegram",
    name: "Telegram",
    icon: "✈️",
    color: "from-blue-500 to-cyan-500",
    description:
      "Free bot API. Get instant notifications and submit tasks from Telegram.",
    fields: [
      {
        key: "bot_token",
        label: "Bot Token",
        placeholder: "123456:ABC-DEF...",
        secret: true,
      },
    ],
    docs_url: "https://core.telegram.org/bots#botfather",
    setup_steps: [
      "Message @BotFather on Telegram",
      "Send /newbot and follow the prompts",
      "Copy the bot token and paste it below",
      "Message your bot and send /start",
    ],
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    icon: "📱",
    color: "from-green-500 to-emerald-500",
    description: "Via Twilio. Send and receive messages on WhatsApp.",
    fields: [
      {
        key: "account_sid",
        label: "Account SID",
        placeholder: "ACxxxxxxxxxxxxxxxx",
      },
      {
        key: "auth_token",
        label: "Auth Token",
        placeholder: "your_auth_token",
        secret: true,
      },
      {
        key: "from_number",
        label: "From Number",
        placeholder: "whatsapp:+14155238886",
      },
    ],
    docs_url: "https://www.twilio.com/whatsapp",
    setup_steps: [
      "Sign up at twilio.com",
      "Enable WhatsApp Sandbox in Console",
      "Copy Account SID and Auth Token",
      "Set webhook URL to /api/messaging/whatsapp/webhook",
    ],
  },
  {
    id: "webhook",
    name: "Webhook",
    icon: "🔗",
    color: "from-yellow-500 to-orange-500",
    description: "Generic webhook for Slack, Discord, or custom endpoints.",
    fields: [
      {
        key: "webhook_url",
        label: "Webhook URL",
        placeholder: "https://hooks.slack.com/...",
      },
      {
        key: "secret",
        label: "Secret (optional)",
        placeholder: "webhook_secret",
      },
    ],
    docs_url: "",
    setup_steps: [
      "Get a webhook URL from your service (Slack, Discord, etc.)",
      "Paste it below",
      "UnClaude will POST task notifications to this URL",
    ],
  },
];

function PlatformCard({
  config,
  status,
  onSetup,
  onRemove,
  onTest,
}: {
  config: PlatformConfig;
  status: PlatformStatus | null;
  onSetup: (
    platformId: string,
    fields: Record<string, string>,
  ) => Promise<void>;
  onRemove: (platformId: string) => Promise<void>;
  onTest: (platformId: string) => void;
}) {
  const isConfigured = status?.configured ?? false;
  const [expanded, setExpanded] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  const handleSetup = async () => {
    setSaving(true);
    try {
      await onSetup(config.id, fieldValues);
      setExpanded(false);
      setFieldValues({});
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 transition-colors">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`p-2.5 rounded-xl bg-gradient-to-br ${config.color} text-lg`}
              >
                {config.icon}
              </div>
              <div>
                <CardTitle className="text-base">{config.name}</CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  {config.description}
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {isConfigured ? (
                <Badge className="bg-green-600/20 text-green-400 border-green-500/30">
                  <CheckCircle2 className="h-3 w-3 mr-1" /> Connected
                </Badge>
              ) : (
                <Badge
                  variant="outline"
                  className="text-zinc-500 border-zinc-700"
                >
                  Not configured
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* Connected state */}
          {isConfigured && !expanded && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-400">
                {status?.registered_chats ?? 0} registered chat
                {(status?.registered_chats ?? 0) !== 1 ? "s" : ""}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onTest(config.id)}
                  className="border-zinc-700 text-xs"
                >
                  <Send className="h-3 w-3 mr-1" /> Test
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onRemove(config.id)}
                  className="text-red-400 hover:text-red-300 text-xs"
                >
                  <Trash2 className="h-3 w-3 mr-1" /> Remove
                </Button>
              </div>
            </div>
          )}

          {/* Setup form */}
          {!isConfigured || expanded ? (
            <div className="space-y-3">
              {/* Steps */}
              <div className="bg-zinc-800/50 rounded-lg p-3">
                <p className="text-xs font-medium text-zinc-300 mb-2">
                  Setup steps:
                </p>
                <ol className="text-xs text-zinc-400 space-y-1 list-decimal list-inside">
                  {config.setup_steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </div>

              {/* Fields */}
              {config.fields.map((field) => (
                <div key={field.key}>
                  <label className="text-xs text-zinc-400 mb-1 block">
                    {field.label}
                  </label>
                  <div className="flex gap-2">
                    <Input
                      type={
                        field.secret && !showSecrets[field.key]
                          ? "password"
                          : "text"
                      }
                      placeholder={field.placeholder}
                      value={fieldValues[field.key] || ""}
                      onChange={(e) =>
                        setFieldValues((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                      className="bg-zinc-800 border-zinc-700 text-sm"
                    />
                    {field.secret && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() =>
                          setShowSecrets((prev) => ({
                            ...prev,
                            [field.key]: !prev[field.key],
                          }))
                        }
                        className="shrink-0"
                      >
                        {showSecrets[field.key] ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                  </div>
                </div>
              ))}

              <div className="flex gap-2">
                <Button
                  onClick={handleSetup}
                  disabled={
                    saving ||
                    config.fields.some((f) => !fieldValues[f.key]?.trim())
                  }
                  className="bg-blue-600 hover:bg-blue-700"
                  size="sm"
                >
                  {saving ? "Connecting..." : "Connect"}
                </Button>
                {config.docs_url && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-zinc-700"
                    asChild
                  >
                    <a href={config.docs_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-3 w-3 mr-1" /> Docs
                    </a>
                  </Button>
                )}
                {expanded && isConfigured && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setExpanded(false)}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ══════════════════════════════════════════════════════
// ██  MESSAGING PAGE
// ══════════════════════════════════════════════════════

export default function MessagingPage() {
  const [status, setStatus] = useState<MessagingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [testModal, setTestModal] = useState<string | null>(null);
  const [testChatId, setTestChatId] = useState("");
  const [testSending, setTestSending] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/messaging/status");
      const data = await res.json();
      setStatus(data);
    } catch (err) {
      console.error("Failed to load messaging status:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 10000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  const handleSetup = async (
    platformId: string,
    fields: Record<string, string>,
  ) => {
    try {
      const res = await fetch(`/api/messaging/${platformId}/setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });
      const data = await res.json();
      if (data.ok) {
        await loadStatus();
      }
    } catch (err) {
      console.error("Setup failed:", err);
    }
  };

  const handleRemove = async (platformId: string) => {
    try {
      await fetch(`/api/messaging/${platformId}`, { method: "DELETE" });
      await loadStatus();
    } catch (err) {
      console.error("Remove failed:", err);
    }
  };

  const handleTest = (platformId: string) => {
    setTestModal(platformId);
    setTestChatId("");
    setTestResult(null);
  };

  const sendTest = async () => {
    if (!testModal || !testChatId.trim()) return;
    setTestSending(true);
    setTestResult(null);
    try {
      const res = await fetch("/api/messaging/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: testModal,
          chat_id: testChatId,
          text: "🤖 UnClaude Test — Your messaging integration is working!",
        }),
      });
      const data = await res.json();
      setTestResult(data.ok ? "success" : "failed");
    } catch {
      setTestResult("failed");
    } finally {
      setTestSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span className="text-2xl">💬</span> Messaging
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Connect Telegram, WhatsApp, or webhooks to chat with UnClaude on the
            go
          </p>
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={loadStatus}
          className="border-zinc-700"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Body */}
      <ScrollArea className="flex-1" style={{ height: "calc(100vh - 100px)" }}>
        <div className="p-6 space-y-6 max-w-3xl mx-auto">
          {/* Info Banner */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="bg-gradient-to-r from-blue-600/10 to-purple-600/10 border-blue-500/20">
              <CardContent className="p-4 flex items-start gap-4">
                <div className="text-3xl">🤖</div>
                <div>
                  <p className="text-sm text-white font-medium">
                    Chat with your AI agent anywhere
                  </p>
                  <p className="text-xs text-zinc-400 mt-1 leading-relaxed">
                    Connect a messaging platform to submit tasks, check status,
                    and get notifications when tasks complete — all from your
                    phone. Use <code className="text-blue-400">/task</code> to
                    submit tasks, <code className="text-blue-400">/status</code>{" "}
                    to check the daemon, or just send a message to chat.
                  </p>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Platform Cards */}
          {PLATFORMS.map((platform) => (
            <div key={platform.id}>
              <PlatformCard
                config={platform}
                status={status?.platforms?.[platform.id] ?? null}
                onSetup={handleSetup}
                onRemove={handleRemove}
                onTest={handleTest}
              />
            </div>
          ))}

          {/* Available Commands Reference */}
          <Card className="bg-zinc-900/60 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-blue-500" /> Bot Commands
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                {[
                  { cmd: "/start", desc: "Register for notifications" },
                  { cmd: "/stop", desc: "Unregister from notifications" },
                  { cmd: "/task <desc>", desc: "Submit a task to the agent" },
                  { cmd: "/status", desc: "Check daemon status" },
                  { cmd: "/usage", desc: "Token usage summary" },
                  { cmd: "/jobs", desc: "List recent tasks" },
                  { cmd: "/help", desc: "Show all commands" },
                ].map((c) => (
                  <div key={c.cmd} className="flex items-center gap-2 py-1">
                    <code className="text-blue-400 bg-zinc-800 px-1.5 py-0.5 rounded text-[11px]">
                      {c.cmd}
                    </code>
                    <span className="text-zinc-400">{c.desc}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </ScrollArea>

      {/* Test Message Modal */}
      {testModal && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
          onClick={() => setTestModal(null)}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-md w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold mb-3">
              Test {testModal.charAt(0).toUpperCase() + testModal.slice(1)}
            </h3>
            <p className="text-sm text-zinc-400 mb-4">
              {testModal === "telegram"
                ? "Enter your Telegram chat ID (send /start to the bot first)"
                : testModal === "whatsapp"
                  ? "Enter the WhatsApp number (e.g., whatsapp:+1234567890)"
                  : "Enter a chat/channel ID"}
            </p>
            <Input
              placeholder={
                testModal === "telegram"
                  ? "123456789"
                  : testModal === "whatsapp"
                    ? "whatsapp:+1234567890"
                    : "channel-id"
              }
              value={testChatId}
              onChange={(e) => setTestChatId(e.target.value)}
              className="bg-zinc-800 border-zinc-700 mb-3"
            />
            {testResult && (
              <div
                className={`text-sm mb-3 ${
                  testResult === "success" ? "text-green-400" : "text-red-400"
                }`}
              >
                {testResult === "success"
                  ? "✓ Message sent successfully!"
                  : "✗ Failed to send. Check your config."}
              </div>
            )}
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => setTestModal(null)}>
                Cancel
              </Button>
              <Button
                onClick={sendTest}
                disabled={!testChatId.trim() || testSending}
                className="bg-blue-600 hover:bg-blue-700"
              >
                {testSending ? "Sending..." : "Send Test"}
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
