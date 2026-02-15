"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  ArrowLeft,
  Check,
  Sparkles,
  ExternalLink,
  Loader2,
  Plus,
  Send,
  Play,
  Wand2,
  List,
  Eye,
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
import { ScrollArea } from "@/components/ui/scroll-area";

const providers = [
  {
    id: "gemini",
    name: "Google Gemini",
    icon: "🌟",
    color: "from-blue-500 to-cyan-500",
    envVar: "GEMINI_API_KEY",
    docsUrl: "https://ai.google.dev/",
    description: "Fast, capable, and free tier available",
  },
  {
    id: "openai",
    name: "OpenAI",
    icon: "🤖",
    color: "from-green-500 to-emerald-500",
    envVar: "OPENAI_API_KEY",
    docsUrl: "https://platform.openai.com/",
    description: "GPT-4o and GPT-4 Turbo models",
  },
  {
    id: "anthropic",
    name: "Anthropic Claude",
    icon: "🧠",
    color: "from-orange-500 to-amber-500",
    envVar: "ANTHROPIC_API_KEY",
    docsUrl: "https://console.anthropic.com/",
    description: "Claude Sonnet and Opus models",
  },
  {
    id: "ollama",
    name: "Ollama (Local)",
    icon: "🏠",
    color: "from-purple-500 to-pink-500",
    envVar: null,
    docsUrl: "https://ollama.ai/",
    description: "Run models locally, no API key needed",
  },
];

const TOTAL_STEPS = 8; // 0-7

interface OnboardingProps {
  onComplete: () => void;
}

export default function Onboarding({ onComplete }: OnboardingProps) {
  // Step: 0=welcome, 1=provider, 2=model, 3=apikey, 4=messaging, 5=soul, 6=daemon, 7=done
  const [step, setStep] = useState(0);

  // Provider setup
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [customModels, setCustomModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [customModelInput, setCustomModelInput] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Messaging setup
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramSaving, setTelegramSaving] = useState(false);
  const [telegramBot, setTelegramBot] = useState<string | null>(null);
  const [telegramError, setTelegramError] = useState("");

  // Soul setup
  const [soulMode, setSoulMode] = useState<"describe" | "pick" | null>(null);
  const [soulDescription, setSoulDescription] = useState("");
  const [soulAgentName, setSoulAgentName] = useState("UnClaude");
  const [soulGenerating, setSoulGenerating] = useState(false);
  const [soulPreview, setSoulPreview] = useState<string | null>(null);
  const [soulSaving, setSoulSaving] = useState(false);
  const [soulError, setSoulError] = useState("");
  const [soulSaved, setSoulSaved] = useState(false);

  // Preset behaviors
  const [presetBehaviors, setPresetBehaviors] = useState<
    {
      key: string;
      name: string;
      label: string;
      interval: string;
      default: boolean;
    }[]
  >([]);
  const [selectedBehaviors, setSelectedBehaviors] = useState<string[]>([]);

  // Daemon
  const [daemonStarting, setDaemonStarting] = useState(false);
  const [daemonStarted, setDaemonStarted] = useState(false);
  const [daemonError, setDaemonError] = useState("");

  // Setup summary
  const [setupStatus, setSetupStatus] = useState<{
    provider: boolean;
    messaging: boolean;
    soul: boolean;
    daemon: boolean;
  }>({ provider: false, messaging: false, soul: false, daemon: false });

  const provider = providers.find((p) => p.id === selectedProvider);

  // Fetch models when provider is selected
  useEffect(() => {
    if (selectedProvider && step === 2) {
      fetchModels(selectedProvider);
    }
  }, [selectedProvider, step]);

  // Load preset behaviors when entering soul step
  useEffect(() => {
    if (step === 5 && soulMode === "pick" && presetBehaviors.length === 0) {
      loadPresetBehaviors();
    }
  }, [step, soulMode]);

  const fetchModels = async (providerId: string) => {
    setLoadingModels(true);
    try {
      const res = await fetch(`/api/settings/models/${providerId}`);
      const data = await res.json();
      setModels(data.models || []);
      setCustomModels(data.custom_models || []);
      if (data.default && !selectedModel) {
        setSelectedModel(data.default);
      }
    } catch {
      console.error("Failed to fetch models");
    } finally {
      setLoadingModels(false);
    }
  };

  const loadPresetBehaviors = async () => {
    try {
      const res = await fetch("/api/setup/soul/behaviors");
      const data = await res.json();
      setPresetBehaviors(data.behaviors || []);
      const defaults = (data.behaviors || [])
        .filter((b: { default: boolean }) => b.default)
        .map((b: { key: string }) => b.key);
      setSelectedBehaviors(defaults);
    } catch {
      console.error("Failed to load behaviors");
    }
  };

  const handleSelectProvider = (id: string) => {
    setSelectedProvider(id);
    setSelectedModel(null);
    setStep(2);
  };

  const handleSelectModel = () => {
    const p = providers.find((pr) => pr.id === selectedProvider);
    if (p?.envVar === null) {
      handleSaveOllama();
    } else {
      setStep(3);
    }
  };

  const handleSaveOllama = async () => {
    setSaving(true);
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_provider: selectedProvider,
          provider_model: { [selectedProvider!]: selectedModel },
        }),
      });
      setSetupStatus((s) => ({ ...s, provider: true }));
      setStep(4);
    } catch {
      setError("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleAddCustomModel = async () => {
    if (!customModelInput.trim() || !selectedProvider) return;
    try {
      const res = await fetch("/api/settings/models/custom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: selectedProvider,
          model: customModelInput.trim(),
        }),
      });
      const data = await res.json();
      if (data.success) {
        setCustomModels([...customModels, customModelInput.trim()]);
        setSelectedModel(customModelInput.trim());
        setCustomModelInput("");
      }
    } catch {
      console.error("Failed to add custom model");
    }
  };

  const handleSaveKey = async () => {
    if (!apiKey.trim()) {
      setError("Please enter an API key");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_provider: selectedProvider,
          provider_model: { [selectedProvider!]: selectedModel },
          api_key: { [selectedProvider!]: apiKey },
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSetupStatus((s) => ({ ...s, provider: true }));
        setStep(4);
      } else {
        setError(data.message || "Failed to save");
      }
    } catch {
      setError("Failed to save API key");
    } finally {
      setSaving(false);
    }
  };

  const handleSetupTelegram = async () => {
    if (!telegramToken.trim() || !telegramToken.includes(":")) {
      setTelegramError(
        "Please enter a valid bot token (format: 123456:ABC-DEF...)",
      );
      return;
    }
    setTelegramSaving(true);
    setTelegramError("");
    try {
      const res = await fetch("/api/messaging/telegram/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_token: telegramToken }),
      });
      const data = await res.json();
      if (data.ok) {
        setTelegramBot(data.bot?.username || "your bot");
        setSetupStatus((s) => ({ ...s, messaging: true }));
      } else {
        setTelegramError(data.error || "Failed to verify token");
      }
    } catch {
      setTelegramError("Failed to connect to Telegram");
    } finally {
      setTelegramSaving(false);
    }
  };

  const handleGenerateSoul = async () => {
    if (!soulDescription.trim()) {
      setSoulError("Describe what you want your agent to do");
      return;
    }
    setSoulGenerating(true);
    setSoulError("");
    setSoulPreview(null);
    try {
      const res = await fetch("/api/setup/soul/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: soulDescription,
          agent_name: soulAgentName,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSoulPreview(data.content);
      } else {
        setSoulError(
          data.detail || "Generation failed — try simpler description",
        );
      }
    } catch {
      setSoulError("Failed to generate soul");
    } finally {
      setSoulGenerating(false);
    }
  };

  const handleGeneratePreset = async () => {
    if (selectedBehaviors.length === 0) {
      setSoulError("Select at least one behavior");
      return;
    }
    setSoulGenerating(true);
    setSoulError("");
    try {
      const res = await fetch("/api/setup/soul/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: soulAgentName,
          behaviors: selectedBehaviors,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSoulPreview(data.content);
      } else {
        setSoulError(data.detail || "Generation failed");
      }
    } catch {
      setSoulError("Failed to generate soul");
    } finally {
      setSoulGenerating(false);
    }
  };

  const handleSaveSoul = async () => {
    if (!soulPreview) return;
    setSoulSaving(true);
    setSoulError("");
    try {
      const res = await fetch("/api/setup/soul/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: soulPreview }),
      });
      const data = await res.json();
      if (data.success) {
        setSoulSaved(true);
        setSetupStatus((s) => ({ ...s, soul: true }));
      } else {
        setSoulError(data.detail || "Failed to save");
      }
    } catch {
      setSoulError("Failed to save soul");
    } finally {
      setSoulSaving(false);
    }
  };

  const handleStartDaemon = async () => {
    setDaemonStarting(true);
    setDaemonError("");
    try {
      const res = await fetch("/api/setup/daemon/start", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setDaemonStarted(true);
        setSetupStatus((s) => ({ ...s, daemon: true }));
      } else {
        setDaemonError(data.detail || "Failed to start daemon");
      }
    } catch {
      setDaemonError("Failed to start daemon");
    } finally {
      setDaemonStarting(false);
    }
  };

  const handleFinish = async () => {
    if (selectedProvider) {
      try {
        await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            default_provider: selectedProvider,
            provider_model: { [selectedProvider]: selectedModel },
          }),
        });
      } catch {
        /* best effort */
      }
    }
    onComplete();
  };

  const toggleBehavior = (key: string) => {
    setSelectedBehaviors((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const progressSteps = Array.from({ length: TOTAL_STEPS }, (_, i) => i);

  return (
    <div className="fixed inset-0 bg-zinc-950 flex items-center justify-center p-6 z-50">
      {/* Background gradient */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-1/4 w-1/2 h-1/2 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 -right-1/4 w-1/2 h-1/2 bg-purple-500/10 rounded-full blur-3xl" />
      </div>

      {/* Progress indicator */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 flex gap-2">
        {progressSteps.map((i) => (
          <div
            key={i}
            className={`h-1.5 w-8 rounded-full transition-colors duration-300 ${
              i <= step ? "bg-blue-500" : "bg-zinc-800"
            }`}
          />
        ))}
      </div>

      <AnimatePresence mode="wait">
        {/* ────────── Step 0: Welcome ────────── */}
        {step === 0 && (
          <motion.div
            key="welcome"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative text-center max-w-lg"
          >
            <motion.div
              animate={{ rotate: [0, 5, -5, 0] }}
              transition={{ repeat: Infinity, duration: 2 }}
              className="text-8xl mb-8"
            >
              🤖
            </motion.div>
            <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
              Welcome to UnClaude
            </h1>
            <p className="text-zinc-400 mb-2 text-lg">
              Your open-source AI coding assistant.
            </p>
            <p className="text-zinc-500 mb-8">
              We&apos;ll get you set up in a few simple steps — no coding
              required.
            </p>
            <Button
              size="lg"
              onClick={() => setStep(1)}
              className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 h-14 px-8 text-lg"
            >
              Get Started
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </motion.div>
        )}

        {/* ────────── Step 1: Select Provider ────────── */}
        {step === 1 && (
          <motion.div
            key="providers"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-2xl"
          >
            <div className="text-center mb-8">
              <Sparkles className="w-12 h-12 mx-auto mb-4 text-purple-400" />
              <h2 className="text-2xl font-bold mb-2">
                Choose Your AI Provider
              </h2>
              <p className="text-zinc-400">
                Which AI brain should power your agent?
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {providers.map((p) => (
                <motion.button
                  key={p.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => handleSelectProvider(p.id)}
                  className={`p-6 rounded-xl border text-left transition-all ${
                    selectedProvider === p.id
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <span className="text-3xl">{p.icon}</span>
                    {!p.envVar && (
                      <span className="text-xs bg-green-600/20 text-green-400 px-2 py-1 rounded">
                        No key needed
                      </span>
                    )}
                  </div>
                  <h3 className="font-semibold mb-1">{p.name}</h3>
                  <p className="text-sm text-zinc-500">{p.description}</p>
                </motion.button>
              ))}
            </div>
          </motion.div>
        )}

        {/* ────────── Step 2: Select Model ────────── */}
        {step === 2 && provider && (
          <motion.div
            key="models"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-lg"
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="text-center">
                <div className="text-5xl mb-4">{provider.icon}</div>
                <CardTitle>Select a Model</CardTitle>
                <CardDescription>
                  Choose or add a model for {provider.name}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {loadingModels ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                  </div>
                ) : (
                  <>
                    <ScrollArea className="h-48">
                      <div className="space-y-2 pr-4">
                        {customModels.map((model) => (
                          <button
                            key={model}
                            onClick={() => setSelectedModel(model)}
                            className={`w-full text-left px-4 py-3 rounded-lg border transition-all flex items-center justify-between ${
                              selectedModel === model
                                ? "border-blue-500 bg-blue-500/10"
                                : "border-zinc-800 bg-zinc-800/50 hover:border-zinc-700"
                            }`}
                          >
                            <span>{model}</span>
                            <span className="text-xs bg-purple-600/20 text-purple-400 px-2 py-0.5 rounded">
                              custom
                            </span>
                          </button>
                        ))}
                        {models.map((model) => (
                          <button
                            key={model}
                            onClick={() => setSelectedModel(model)}
                            className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
                              selectedModel === model
                                ? "border-blue-500 bg-blue-500/10"
                                : "border-zinc-800 bg-zinc-800/50 hover:border-zinc-700"
                            }`}
                          >
                            {model}
                          </button>
                        ))}
                      </div>
                    </ScrollArea>

                    <div className="flex gap-2">
                      <Input
                        placeholder="Add custom model..."
                        value={customModelInput}
                        onChange={(e) => setCustomModelInput(e.target.value)}
                        onKeyDown={(e) =>
                          e.key === "Enter" && handleAddCustomModel()
                        }
                        className="bg-zinc-800 border-zinc-700"
                      />
                      <Button
                        size="icon"
                        variant="outline"
                        onClick={handleAddCustomModel}
                        disabled={!customModelInput.trim()}
                      >
                        <Plus className="w-4 h-4" />
                      </Button>
                    </div>
                  </>
                )}

                <div className="flex gap-3 pt-2">
                  <Button
                    variant="outline"
                    onClick={() => setStep(1)}
                    className="flex-1"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                  <Button
                    onClick={handleSelectModel}
                    disabled={!selectedModel}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                  >
                    Continue
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ────────── Step 3: Enter API Key ────────── */}
        {step === 3 && provider && (
          <motion.div
            key="apikey"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-md"
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="text-center">
                <div className="text-5xl mb-4">{provider.icon}</div>
                <CardTitle>{provider.name}</CardTitle>
                <CardDescription>
                  Enter your API key for {selectedModel}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Input
                    type="password"
                    placeholder="Paste your API key here"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="bg-zinc-800 border-zinc-700 h-12"
                  />
                  {error && (
                    <p className="text-sm text-red-400 mt-2">{error}</p>
                  )}
                </div>

                <a
                  href={provider.docsUrl}
                  target="_blank"
                  className="flex items-center justify-center gap-2 text-sm text-blue-400 hover:text-blue-300"
                >
                  Get an API key from {provider.name}
                  <ExternalLink className="w-4 h-4" />
                </a>

                <div className="flex gap-3 pt-2">
                  <Button
                    variant="outline"
                    onClick={() => setStep(2)}
                    className="flex-1"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                  <Button
                    onClick={handleSaveKey}
                    disabled={saving}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                  >
                    {saving ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      "Continue"
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ────────── Step 4: Messaging (Telegram) ────────── */}
        {step === 4 && (
          <motion.div
            key="messaging"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-md"
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="text-center">
                <div className="text-5xl mb-4">✈️</div>
                <CardTitle>Stay Connected</CardTitle>
                <CardDescription>
                  Connect Telegram so your agent can message you — task updates,
                  summaries, and alerts.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {telegramBot ? (
                  <div className="text-center py-4">
                    <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
                      <Check className="w-6 h-6 text-green-400" />
                    </div>
                    <p className="text-green-400 font-medium">
                      Connected to @{telegramBot}
                    </p>
                    <p className="text-zinc-500 text-sm mt-1">
                      Send /start to your bot on Telegram
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="bg-zinc-800/50 rounded-lg p-4 text-sm text-zinc-400 space-y-2">
                      <p className="font-medium text-zinc-300">Quick setup:</p>
                      <ol className="list-decimal list-inside space-y-1">
                        <li>
                          Open Telegram and message{" "}
                          <span className="text-blue-400">@BotFather</span>
                        </li>
                        <li>
                          Send <span className="text-blue-400">/newbot</span>{" "}
                          and follow prompts
                        </li>
                        <li>Copy the bot token and paste below</li>
                      </ol>
                    </div>

                    <Input
                      type="password"
                      placeholder="Paste bot token (123456:ABC-DEF...)"
                      value={telegramToken}
                      onChange={(e) => setTelegramToken(e.target.value)}
                      className="bg-zinc-800 border-zinc-700 h-12"
                    />
                    {telegramError && (
                      <p className="text-sm text-red-400">{telegramError}</p>
                    )}

                    <Button
                      onClick={handleSetupTelegram}
                      disabled={telegramSaving || !telegramToken.trim()}
                      className="w-full bg-gradient-to-r from-blue-600 to-cyan-600"
                    >
                      {telegramSaving ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      ) : (
                        <Send className="w-4 h-4 mr-2" />
                      )}
                      Connect Telegram
                    </Button>
                  </>
                )}

                <div className="flex gap-3 pt-2">
                  <Button
                    variant="outline"
                    onClick={() => setStep(3)}
                    className="flex-1"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                  <Button
                    onClick={() => setStep(5)}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                  >
                    {telegramBot ? "Continue" : "Skip for now"}
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ────────── Step 5: Soul ────────── */}
        {step === 5 && (
          <motion.div
            key="soul"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-xl"
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="text-center">
                <div className="text-5xl mb-4">🧬</div>
                <CardTitle>Give Your Agent a Soul</CardTitle>
                <CardDescription>
                  The soul defines your agent&apos;s personality and what it
                  does on its own — without you asking.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Soul saved confirmation */}
                {soulSaved ? (
                  <div className="text-center py-4">
                    <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
                      <Check className="w-6 h-6 text-green-400" />
                    </div>
                    <p className="text-green-400 font-medium">Soul saved!</p>
                    <p className="text-zinc-500 text-sm mt-1">
                      Changes are picked up live — edit anytime
                    </p>
                  </div>
                ) : soulPreview ? (
                  /* Soul preview */
                  <>
                    <div className="flex items-center gap-2 mb-2">
                      <Eye className="w-4 h-4 text-purple-400" />
                      <span className="text-sm font-medium text-purple-400">
                        Preview
                      </span>
                    </div>
                    <ScrollArea className="h-64 rounded-lg bg-zinc-800/50 border border-zinc-700">
                      <pre className="p-4 text-xs text-zinc-300 whitespace-pre-wrap font-mono">
                        {soulPreview}
                      </pre>
                    </ScrollArea>
                    {soulError && (
                      <p className="text-sm text-red-400">{soulError}</p>
                    )}
                    <div className="flex gap-3">
                      <Button
                        variant="outline"
                        onClick={() => setSoulPreview(null)}
                        className="flex-1"
                      >
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Try Again
                      </Button>
                      <Button
                        onClick={handleSaveSoul}
                        disabled={soulSaving}
                        className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600"
                      >
                        {soulSaving ? (
                          <Loader2 className="w-4 h-4 animate-spin mr-2" />
                        ) : (
                          <Check className="w-4 h-4 mr-2" />
                        )}
                        Save Soul
                      </Button>
                    </div>
                  </>
                ) : soulMode === null ? (
                  /* Mode selection */
                  <>
                    <div className="space-y-2 mb-2">
                      <Input
                        placeholder="Agent name"
                        value={soulAgentName}
                        onChange={(e) => setSoulAgentName(e.target.value)}
                        className="bg-zinc-800 border-zinc-700"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => setSoulMode("describe")}
                        className="p-5 rounded-xl border border-zinc-800 bg-zinc-900/50 hover:border-purple-500/50 text-left transition-all"
                      >
                        <Wand2 className="w-8 h-8 text-purple-400 mb-3" />
                        <h3 className="font-semibold mb-1">
                          Describe in English
                        </h3>
                        <p className="text-sm text-zinc-500">
                          Tell us what you want and AI will create the soul
                        </p>
                      </motion.button>
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => setSoulMode("pick")}
                        className="p-5 rounded-xl border border-zinc-800 bg-zinc-900/50 hover:border-blue-500/50 text-left transition-all"
                      >
                        <List className="w-8 h-8 text-blue-400 mb-3" />
                        <h3 className="font-semibold mb-1">Pick from List</h3>
                        <p className="text-sm text-zinc-500">
                          Choose from pre-built behaviors with toggles
                        </p>
                      </motion.button>
                    </div>
                  </>
                ) : soulMode === "describe" ? (
                  /* Natural language input */
                  <>
                    <p className="text-sm text-zinc-400">
                      Just tell us what you want your agent to do — in plain
                      English.
                    </p>
                    <textarea
                      placeholder={
                        'Example: "Check my code for bugs every few hours, be social on Moltbook, and send me a summary at night"'
                      }
                      value={soulDescription}
                      onChange={(e) => setSoulDescription(e.target.value)}
                      rows={4}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg p-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-purple-500/50 resize-none"
                    />
                    {soulError && (
                      <p className="text-sm text-red-400">{soulError}</p>
                    )}
                    <div className="flex gap-3">
                      <Button
                        variant="outline"
                        onClick={() => setSoulMode(null)}
                        className="flex-1"
                      >
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Back
                      </Button>
                      <Button
                        onClick={handleGenerateSoul}
                        disabled={soulGenerating || !soulDescription.trim()}
                        className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600"
                      >
                        {soulGenerating ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin mr-2" />
                            Generating...
                          </>
                        ) : (
                          <>
                            <Wand2 className="w-4 h-4 mr-2" />
                            Generate Soul
                          </>
                        )}
                      </Button>
                    </div>
                  </>
                ) : (
                  /* Pick from preset list */
                  <>
                    <p className="text-sm text-zinc-400 mb-2">
                      Toggle the behaviors you want your agent to do
                      automatically:
                    </p>
                    {presetBehaviors.length === 0 ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {presetBehaviors.map((b) => (
                          <button
                            key={b.key}
                            onClick={() => toggleBehavior(b.key)}
                            className={`w-full text-left px-4 py-3 rounded-lg border transition-all flex items-center justify-between ${
                              selectedBehaviors.includes(b.key)
                                ? "border-blue-500 bg-blue-500/10"
                                : "border-zinc-800 bg-zinc-800/50 hover:border-zinc-700"
                            }`}
                          >
                            <div>
                              <span className="font-medium text-sm">
                                {b.label}
                              </span>
                              <span className="text-xs text-zinc-500 ml-2">
                                every {b.interval}
                              </span>
                            </div>
                            <div
                              className={`w-5 h-5 rounded-md border flex items-center justify-center ${
                                selectedBehaviors.includes(b.key)
                                  ? "bg-blue-500 border-blue-500"
                                  : "border-zinc-600"
                              }`}
                            >
                              {selectedBehaviors.includes(b.key) && (
                                <Check className="w-3 h-3 text-white" />
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                    {soulError && (
                      <p className="text-sm text-red-400">{soulError}</p>
                    )}
                    <div className="flex gap-3 pt-1">
                      <Button
                        variant="outline"
                        onClick={() => setSoulMode(null)}
                        className="flex-1"
                      >
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Back
                      </Button>
                      <Button
                        onClick={handleGeneratePreset}
                        disabled={
                          soulGenerating || selectedBehaviors.length === 0
                        }
                        className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                      >
                        {soulGenerating ? (
                          <Loader2 className="w-4 h-4 animate-spin mr-2" />
                        ) : (
                          <Sparkles className="w-4 h-4 mr-2" />
                        )}
                        Preview Soul
                      </Button>
                    </div>
                  </>
                )}

                {/* Bottom navigation (only when not in sub-flow) */}
                {(soulSaved || soulMode === null) && (
                  <div className="flex gap-3 pt-2 border-t border-zinc-800">
                    <Button
                      variant="outline"
                      onClick={() => setStep(4)}
                      className="flex-1"
                    >
                      <ArrowLeft className="w-4 h-4 mr-2" />
                      Back
                    </Button>
                    <Button
                      onClick={() => setStep(6)}
                      className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                    >
                      {soulSaved ? "Continue" : "Skip for now"}
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ────────── Step 6: Daemon ────────── */}
        {step === 6 && (
          <motion.div
            key="daemon"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="relative w-full max-w-md"
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="text-center">
                <div className="text-5xl mb-4">⚡</div>
                <CardTitle>Go Autonomous</CardTitle>
                <CardDescription>
                  Start the background daemon so your agent runs 24/7 — picking
                  up tasks and executing soul behaviors automatically.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {daemonStarted ? (
                  <div className="text-center py-4">
                    <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
                      <Check className="w-6 h-6 text-green-400" />
                    </div>
                    <p className="text-green-400 font-medium">
                      Daemon is running!
                    </p>
                    <p className="text-zinc-500 text-sm mt-1">
                      Your agent is now working in the background
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="bg-zinc-800/50 rounded-lg p-4 text-sm text-zinc-400 space-y-2">
                      <p>The daemon will:</p>
                      <ul className="list-disc list-inside space-y-1 text-zinc-500">
                        <li>Run proactive behaviors from your soul</li>
                        <li>Process tasks submitted via CLI or Telegram</li>
                        <li>Send you notifications when things happen</li>
                        <li>Work quietly in the background</li>
                      </ul>
                    </div>

                    {daemonError && (
                      <p className="text-sm text-red-400">{daemonError}</p>
                    )}

                    <Button
                      onClick={handleStartDaemon}
                      disabled={daemonStarting}
                      className="w-full bg-gradient-to-r from-green-600 to-emerald-600 h-12"
                    >
                      {daemonStarting ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      ) : (
                        <Play className="w-4 h-4 mr-2" />
                      )}
                      Start Agent Daemon
                    </Button>
                  </>
                )}

                <div className="flex gap-3 pt-2">
                  <Button
                    variant="outline"
                    onClick={() => setStep(5)}
                    className="flex-1"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                  <Button
                    onClick={() => setStep(7)}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                  >
                    {daemonStarted ? "Continue" : "Skip for now"}
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ────────── Step 7: Done ────────── */}
        {step === 7 && (
          <motion.div
            key="done"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="relative text-center max-w-lg"
          >
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", delay: 0.2 }}
              className="w-20 h-20 rounded-full bg-gradient-to-br from-green-500 to-emerald-500 flex items-center justify-center mx-auto mb-6"
            >
              <Check className="w-10 h-10 text-white" />
            </motion.div>
            <h2 className="text-3xl font-bold mb-4">You&apos;re All Set!</h2>

            {/* Summary */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 mb-6 text-left space-y-3">
              <div className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${
                    setupStatus.provider ? "bg-green-500/20" : "bg-zinc-800"
                  }`}
                >
                  {setupStatus.provider ? (
                    <Check className="w-3 h-3 text-green-400" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-zinc-600" />
                  )}
                </div>
                <span className="text-sm">
                  <span className="text-zinc-300 font-medium">
                    AI Provider:{" "}
                  </span>
                  <span className="text-zinc-400">
                    {providers.find((p) => p.id === selectedProvider)?.name ||
                      "—"}{" "}
                    / {selectedModel || "—"}
                  </span>
                </span>
              </div>

              <div className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${
                    setupStatus.messaging ? "bg-green-500/20" : "bg-zinc-800"
                  }`}
                >
                  {setupStatus.messaging ? (
                    <Check className="w-3 h-3 text-green-400" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-zinc-600" />
                  )}
                </div>
                <span className="text-sm">
                  <span className="text-zinc-300 font-medium">Telegram: </span>
                  <span className="text-zinc-400">
                    {telegramBot ? `@${telegramBot}` : "Not connected"}
                  </span>
                </span>
              </div>

              <div className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${
                    setupStatus.soul ? "bg-green-500/20" : "bg-zinc-800"
                  }`}
                >
                  {setupStatus.soul ? (
                    <Check className="w-3 h-3 text-green-400" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-zinc-600" />
                  )}
                </div>
                <span className="text-sm">
                  <span className="text-zinc-300 font-medium">
                    Agent Soul:{" "}
                  </span>
                  <span className="text-zinc-400">
                    {setupStatus.soul ? "Configured" : "Not set"}
                  </span>
                </span>
              </div>

              <div className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center ${
                    setupStatus.daemon ? "bg-green-500/20" : "bg-zinc-800"
                  }`}
                >
                  {setupStatus.daemon ? (
                    <Check className="w-3 h-3 text-green-400" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-zinc-600" />
                  )}
                </div>
                <span className="text-sm">
                  <span className="text-zinc-300 font-medium">Daemon: </span>
                  <span className="text-zinc-400">
                    {setupStatus.daemon ? "Running" : "Not started"}
                  </span>
                </span>
              </div>
            </div>

            <p className="text-zinc-500 mb-6 text-sm">
              You can change any of these in Settings later.
            </p>

            <Button
              size="lg"
              onClick={handleFinish}
              className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 h-14 px-8 text-lg"
            >
              Start Using UnClaude
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
