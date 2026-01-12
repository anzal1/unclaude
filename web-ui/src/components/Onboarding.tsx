"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, ArrowLeft, Check, Sparkles, ExternalLink, Loader2, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

interface OnboardingProps {
  onComplete: () => void;
}

export default function Onboarding({ onComplete }: OnboardingProps) {
  const [step, setStep] = useState(0); // 0: welcome, 1: provider, 2: model, 3: api key, 4: done
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [customModels, setCustomModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [customModelInput, setCustomModelInput] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const provider = providers.find((p) => p.id === selectedProvider);

  // Fetch models when provider is selected
  useEffect(() => {
    if (selectedProvider && step === 2) {
      fetchModels(selectedProvider);
    }
  }, [selectedProvider, step]);

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
    } catch (err) {
      console.error("Failed to fetch models:", err);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSelectProvider = (id: string) => {
    setSelectedProvider(id);
    setSelectedModel(null);
    setStep(2); // Go to model selection
  };

  const handleSelectModel = () => {
    const p = providers.find((pr) => pr.id === selectedProvider);
    if (p?.envVar === null) {
      // Ollama doesn't need a key
      setStep(4);
    } else {
      setStep(3);
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
    } catch (err) {
      console.error("Failed to add custom model:", err);
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
        setStep(4);
      } else {
        setError(data.message || "Failed to save");
      }
    } catch (err) {
      setError("Failed to save API key");
    } finally {
      setSaving(false);
    }
  };

  const handleSetDefault = async () => {
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_provider: selectedProvider,
          provider_model: { [selectedProvider!]: selectedModel },
        }),
      });
    } catch {}
    onComplete();
  };

  return (
    <div className="fixed inset-0 bg-zinc-950 flex items-center justify-center p-6 z-50">
      {/* Background gradient */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-1/4 -left-1/4 w-1/2 h-1/2 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 -right-1/4 w-1/2 h-1/2 bg-purple-500/10 rounded-full blur-3xl" />
      </div>

      {/* Progress indicator */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 flex gap-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1.5 w-8 rounded-full transition-colors ${
              i <= step ? "bg-blue-500" : "bg-zinc-800"
            }`}
          />
        ))}
      </div>

      <AnimatePresence mode="wait">
        {/* Step 0: Welcome */}
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
            <p className="text-zinc-400 mb-8 text-lg">
              Your open-source AI coding assistant. Let&apos;s get you set up in just a few steps.
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

        {/* Step 1: Select Provider */}
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
              <h2 className="text-2xl font-bold mb-2">Choose Your LLM Provider</h2>
              <p className="text-zinc-400">Select which AI provider you want to use</p>
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

        {/* Step 2: Select Model */}
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

                    {/* Add custom model */}
                    <div className="flex gap-2">
                      <Input
                        placeholder="Add custom model..."
                        value={customModelInput}
                        onChange={(e) => setCustomModelInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleAddCustomModel()}
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

        {/* Step 3: Enter API Key */}
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
                  {error && <p className="text-sm text-red-400 mt-2">{error}</p>}
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
                  <Button variant="outline" onClick={() => setStep(2)} className="flex-1">
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back
                  </Button>
                  <Button
                    onClick={handleSaveKey}
                    disabled={saving}
                    className="flex-1 bg-gradient-to-r from-blue-600 to-purple-600"
                  >
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : "Continue"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Step 4: Done */}
        {step === 4 && (
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
            <p className="text-zinc-400 mb-2">
              UnClaude is configured with{" "}
              <span className="text-white font-medium">
                {providers.find((p) => p.id === selectedProvider)?.name}
              </span>
            </p>
            <p className="text-zinc-500 mb-8">
              Model: <span className="text-zinc-300">{selectedModel}</span>
            </p>
            <Button
              size="lg"
              onClick={handleSetDefault}
              className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 h-14 px-8 text-lg"
            >
              Start Chatting
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
