"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Settings,
  Save,
  ExternalLink,
  Check,
  X,
  RefreshCw,
  Plus,
  Sparkles,
  Wand2,
  List,
  Eye,
  Play,
  FileText,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

interface Provider {
  name: string;
  display_name: string;
  models: string[];
  default_model: string;
  env_var: string | null;
  docs_url: string;
}

interface ProviderSettings {
  model: string;
  has_key: boolean;
}

interface Skill {
  name: string;
  description: string;
  steps: number;
}

interface SoulBehavior {
  key: string;
  name: string;
  label: string;
  interval: string;
  default: boolean;
}

interface SettingsPageProps {
  onRunSetupWizard?: () => void;
}

export default function SettingsPage({ onRunSetupWizard }: SettingsPageProps) {
  const [settings, setSettings] = useState<{
    default_provider: string;
    providers: Record<string, ProviderSettings>;
    config_path: string;
  }>({ default_provider: "gemini", providers: {}, config_path: "" });

  const [providers, setProviders] = useState<Provider[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>(
    {},
  );
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [customModelInputs, setCustomModelInputs] = useState<
    Record<string, string>
  >({});

  // Soul management state
  const [soulContent, setSoulContent] = useState<string | null>(null);
  const [soulLoading, setSoulLoading] = useState(false);
  const [soulMode, setSoulMode] = useState<
    "view" | "edit" | "describe" | "pick" | null
  >(null);
  const [soulDescription, setSoulDescription] = useState("");
  const [soulAgentName, setSoulAgentName] = useState("UnClaude");
  const [soulGenerating, setSoulGenerating] = useState(false);
  const [soulPreview, setSoulPreview] = useState<string | null>(null);
  const [soulSaving, setSoulSaving] = useState(false);
  const [soulError, setSoulError] = useState("");
  const [soulBehaviors, setSoulBehaviors] = useState<SoulBehavior[]>([]);
  const [selectedBehaviors, setSelectedBehaviors] = useState<string[]>([]);
  const [soulEditContent, setSoulEditContent] = useState("");

  const addCustomModel = async (providerName: string) => {
    const modelName = customModelInputs[providerName]?.trim();
    if (!modelName) return;

    try {
      const res = await fetch("/api/settings/models/custom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerName, model: modelName }),
      });
      const data = await res.json();
      if (data.success) {
        setCustomModelInputs((prev) => ({ ...prev, [providerName]: "" }));
        setSelectedModels((prev) => ({ ...prev, [providerName]: modelName }));
        loadProviders(); // Refresh model list
      }
    } catch (err) {
      console.error("Failed to add custom model:", err);
    }
  };

  useEffect(() => {
    loadSettings();
    loadProviders();
    loadSkills();
    loadSoul();
    loadSoulBehaviors();
  }, []);

  const loadSettings = async () => {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      setSettings(data);

      const initModels: Record<string, string> = {};
      Object.entries(data.providers || {}).forEach(
        ([name, config]: [string, any]) => {
          initModels[name] = config.model;
        },
      );
      setSelectedModels(initModels);
    } catch (error) {
      console.error("Failed to load settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadProviders = async () => {
    try {
      const res = await fetch("/api/settings/providers");
      const data = await res.json();
      setProviders(data.providers || []);
    } catch (error) {
      console.error("Failed to load providers:", error);
    }
  };

  const loadSkills = async () => {
    try {
      const res = await fetch("/api/settings/skills");
      const data = await res.json();
      setSkills(data.skills || []);
    } catch (error) {
      console.error("Failed to load skills:", error);
    }
  };

  const loadSoul = async () => {
    setSoulLoading(true);
    try {
      const res = await fetch("/api/setup/soul");
      const data = await res.json();
      if (data.content) {
        setSoulContent(data.content);
        setSoulEditContent(data.content);
      }
    } catch (error) {
      console.error("Failed to load soul:", error);
    } finally {
      setSoulLoading(false);
    }
  };

  const loadSoulBehaviors = async () => {
    try {
      const res = await fetch("/api/setup/soul/behaviors");
      const data = await res.json();
      setSoulBehaviors(data.behaviors || []);
      setSelectedBehaviors(
        (data.behaviors || [])
          .filter((b: SoulBehavior) => b.default)
          .map((b: SoulBehavior) => b.key),
      );
    } catch (error) {
      console.error("Failed to load behaviors:", error);
    }
  };

  const generateSoulFromDescription = async () => {
    if (!soulDescription.trim()) return;
    setSoulGenerating(true);
    setSoulError("");
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
        setSoulError(data.detail || "Generation failed");
      }
    } catch (error) {
      setSoulError("Failed to generate soul: " + error);
    } finally {
      setSoulGenerating(false);
    }
  };

  const generateSoulFromPresets = async () => {
    if (selectedBehaviors.length === 0) return;
    setSoulGenerating(true);
    setSoulError("");
    try {
      const res = await fetch("/api/setup/soul/preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: soulAgentName,
          tagline: "Open-source AI agent that actually does things",
          behaviors: selectedBehaviors,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSoulPreview(data.content);
      } else {
        setSoulError(data.detail || "Generation failed");
      }
    } catch (error) {
      setSoulError("Failed to generate soul: " + error);
    } finally {
      setSoulGenerating(false);
    }
  };

  const saveSoul = async (content: string) => {
    setSoulSaving(true);
    setSoulError("");
    try {
      const res = await fetch("/api/setup/soul/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      if (data.success) {
        setSoulContent(content);
        setSoulEditContent(content);
        setSoulPreview(null);
        setSoulMode(null);
        setSoulDescription("");
      } else {
        setSoulError(data.detail || "Save failed");
      }
    } catch (error) {
      setSoulError("Failed to save soul: " + error);
    } finally {
      setSoulSaving(false);
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const payload: any = {
        default_provider: settings.default_provider,
        provider_model: selectedModels,
      };

      const nonEmptyKeys = Object.fromEntries(
        Object.entries(apiKeys).filter(([_, v]) => v && v.trim()),
      );
      if (Object.keys(nonEmptyKeys).length > 0) {
        payload.api_key = nonEmptyKeys;
      }

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (data.success) {
        setApiKeys({});
        loadSettings();
        alert("✅ Settings saved successfully!");
      } else {
        alert("Failed to save: " + (data.message || "Unknown error"));
      }
    } catch (error) {
      alert("Failed to save settings: " + error);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-6 h-6 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span className="text-2xl">⚙️</span> Settings
        </h1>
        <p className="text-sm text-zinc-400 mt-1">Configure your preferences</p>
      </div>

      <ScrollArea
        className="flex-1 overflow-auto"
        style={{ height: "calc(100vh - 100px)" }}
      >
        <div className="max-w-2xl mx-auto space-y-6 px-6 py-6">
          {/* Default Provider */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-lg">🔧 Default Provider</CardTitle>
                <CardDescription>
                  Select which LLM provider to use by default
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Select
                  value={settings.default_provider}
                  onValueChange={(v) =>
                    setSettings({ ...settings, default_provider: v })
                  }
                >
                  <SelectTrigger className="w-full bg-zinc-800 border-zinc-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </CardContent>
            </Card>
          </motion.div>

          {/* Providers */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-lg">
                  🔌 Provider Configuration
                </CardTitle>
                <CardDescription>
                  Configure models and API keys for each provider
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {providers.map((provider) => (
                  <div
                    key={provider.name}
                    className="space-y-3 pb-4 border-b border-zinc-800 last:border-0 last:pb-0"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {provider.display_name}
                        </span>
                        {settings.providers?.[provider.name]?.has_key ? (
                          <Badge
                            variant="default"
                            className="bg-green-600/20 text-green-400 border-green-600/30"
                          >
                            <Check className="w-3 h-3 mr-1" /> Configured
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="bg-zinc-700/50">
                            <X className="w-3 h-3 mr-1" /> Not set
                          </Badge>
                        )}
                      </div>
                      {provider.docs_url && (
                        <a
                          href={provider.docs_url}
                          target="_blank"
                          className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                        >
                          Get API Key <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-zinc-500 mb-1 block">
                          Model
                        </label>
                        <Select
                          value={
                            selectedModels[provider.name] ||
                            settings.providers?.[provider.name]?.model ||
                            provider.default_model ||
                            ""
                          }
                          onValueChange={(v) =>
                            setSelectedModels((prev) => ({
                              ...prev,
                              [provider.name]: v,
                            }))
                          }
                        >
                          <SelectTrigger className="bg-zinc-800 border-zinc-700">
                            <SelectValue placeholder="Select a model..." />
                          </SelectTrigger>
                          <SelectContent>
                            {/* Include current value if not in list */}
                            {(() => {
                              const currentValue =
                                selectedModels[provider.name] ||
                                settings.providers?.[provider.name]?.model;
                              const allModels =
                                currentValue &&
                                !provider.models.includes(currentValue)
                                  ? [currentValue, ...provider.models]
                                  : provider.models;
                              return allModels.map((model) => (
                                <SelectItem key={model} value={model}>
                                  {model}
                                </SelectItem>
                              ));
                            })()}
                          </SelectContent>
                        </Select>
                        <div className="flex gap-1 mt-2">
                          <Input
                            placeholder="Add custom model..."
                            value={customModelInputs[provider.name] || ""}
                            onChange={(e) =>
                              setCustomModelInputs((prev) => ({
                                ...prev,
                                [provider.name]: e.target.value,
                              }))
                            }
                            onKeyDown={(e) =>
                              e.key === "Enter" && addCustomModel(provider.name)
                            }
                            className="bg-zinc-800 border-zinc-700 h-8 text-xs"
                          />
                          <Button
                            size="icon"
                            variant="outline"
                            className="h-8 w-8"
                            onClick={() => addCustomModel(provider.name)}
                            disabled={!customModelInputs[provider.name]?.trim()}
                          >
                            <Plus className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>

                      {provider.env_var && (
                        <div>
                          <label className="text-xs text-zinc-500 mb-1 block">
                            API Key{" "}
                            {settings.providers?.[provider.name]?.has_key &&
                              "(update)"}
                          </label>
                          <Input
                            type="password"
                            placeholder={
                              settings.providers?.[provider.name]?.has_key
                                ? "••••••••"
                                : "Enter API key"
                            }
                            value={apiKeys[provider.name] || ""}
                            onChange={(e) =>
                              setApiKeys((prev) => ({
                                ...prev,
                                [provider.name]: e.target.value,
                              }))
                            }
                            className="bg-zinc-800 border-zinc-700"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </motion.div>

          {/* Save Button */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Button
              onClick={saveSettings}
              disabled={saving}
              className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 h-12"
            >
              {saving ? (
                <RefreshCw className="w-4 h-4 animate-spin mr-2" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              Save All Settings
            </Button>
          </motion.div>

          {/* Skills */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-lg">🎯 Available Skills</CardTitle>
                <CardDescription>
                  Reusable workflows defined in your project
                </CardDescription>
              </CardHeader>
              <CardContent>
                {skills.length === 0 ? (
                  <p className="text-sm text-zinc-500 text-center py-4">
                    No skills configured. Add skills via UNCLAUDE.md or
                    ~/.unclaude/skills/
                  </p>
                ) : (
                  <div className="space-y-2">
                    {skills.map((skill) => (
                      <div
                        key={skill.name}
                        className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50"
                      >
                        <div>
                          <p className="font-medium">{skill.name}</p>
                          <p className="text-xs text-zinc-500">
                            {skill.description || "No description"}
                          </p>
                        </div>
                        <Badge variant="secondary">{skill.steps} steps</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Soul Management */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">✨ Agent Soul</CardTitle>
                    <CardDescription>
                      Define your agent&apos;s personality, behaviors, and
                      autonomous drives
                    </CardDescription>
                  </div>
                  {soulContent && !soulMode && (
                    <Badge
                      variant="default"
                      className="bg-green-600/20 text-green-400 border-green-600/30"
                    >
                      <Check className="w-3 h-3 mr-1" /> Configured
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Current soul status */}
                {soulContent && !soulMode && (
                  <div className="space-y-3">
                    <div className="p-3 bg-zinc-800/50 rounded-lg">
                      <pre className="text-xs text-zinc-400 whitespace-pre-wrap max-h-40 overflow-auto">
                        {soulContent.substring(0, 500)}
                        {soulContent.length > 500 ? "\n..." : ""}
                      </pre>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSoulMode("view")}
                        className="border-zinc-700"
                      >
                        <Eye className="w-3.5 h-3.5 mr-1.5" /> View Full
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulMode("edit");
                          setSoulEditContent(soulContent);
                        }}
                        className="border-zinc-700"
                      >
                        <FileText className="w-3.5 h-3.5 mr-1.5" /> Edit YAML
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSoulMode("describe")}
                        className="border-zinc-700"
                      >
                        <Wand2 className="w-3.5 h-3.5 mr-1.5" /> Regenerate from
                        Description
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSoulMode("pick")}
                        className="border-zinc-700"
                      >
                        <List className="w-3.5 h-3.5 mr-1.5" /> Regenerate from
                        Presets
                      </Button>
                    </div>
                  </div>
                )}

                {/* No soul yet */}
                {!soulContent && !soulMode && !soulLoading && (
                  <div className="text-center py-6 space-y-4">
                    <div className="text-4xl">🫥</div>
                    <p className="text-zinc-400">
                      No soul configured yet. Your agent has no personality or
                      autonomous behaviors.
                    </p>
                    <div className="flex gap-3 justify-center">
                      <Button
                        onClick={() => setSoulMode("describe")}
                        className="bg-gradient-to-r from-purple-600 to-pink-600"
                      >
                        <Wand2 className="w-4 h-4 mr-2" /> Describe in Words
                      </Button>
                      <Button
                        onClick={() => setSoulMode("pick")}
                        variant="outline"
                        className="border-zinc-700"
                      >
                        <List className="w-4 h-4 mr-2" /> Pick from Presets
                      </Button>
                    </div>
                  </div>
                )}

                {soulLoading && (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="w-5 h-5 animate-spin text-zinc-500" />
                  </div>
                )}

                {/* View Full Soul */}
                {soulMode === "view" && (
                  <div className="space-y-3">
                    <div className="p-4 bg-zinc-800/50 rounded-lg">
                      <pre className="text-xs text-zinc-300 whitespace-pre-wrap max-h-96 overflow-auto font-mono">
                        {soulContent}
                      </pre>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSoulMode(null)}
                      className="border-zinc-700"
                    >
                      Close
                    </Button>
                  </div>
                )}

                {/* Edit YAML */}
                {soulMode === "edit" && (
                  <div className="space-y-3">
                    <label className="text-sm text-zinc-400">
                      Edit soul YAML directly:
                    </label>
                    <Textarea
                      value={soulEditContent}
                      onChange={(e) => setSoulEditContent(e.target.value)}
                      className="bg-zinc-800 border-zinc-700 font-mono text-xs min-h-[300px]"
                      placeholder="identity:\n  name: MyAgent\n..."
                    />
                    {soulError && (
                      <p className="text-red-400 text-xs">{soulError}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => saveSoul(soulEditContent)}
                        disabled={soulSaving}
                        className="bg-green-600 hover:bg-green-500"
                      >
                        {soulSaving ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1.5" />
                        ) : (
                          <Save className="w-3.5 h-3.5 mr-1.5" />
                        )}
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulMode(null);
                          setSoulError("");
                        }}
                        className="border-zinc-700"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {/* Generate from Description */}
                {soulMode === "describe" && !soulPreview && (
                  <div className="space-y-4">
                    <p className="text-sm text-zinc-400">
                      Describe what kind of agent you want in plain English. The
                      LLM will generate a complete soul file.
                    </p>
                    <div>
                      <label className="text-xs text-zinc-500 mb-1 block">
                        Agent Name
                      </label>
                      <Input
                        value={soulAgentName}
                        onChange={(e) => setSoulAgentName(e.target.value)}
                        className="bg-zinc-800 border-zinc-700"
                        placeholder="UnClaude"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-zinc-500 mb-1 block">
                        Description
                      </label>
                      <Textarea
                        value={soulDescription}
                        onChange={(e) => setSoulDescription(e.target.value)}
                        className="bg-zinc-800 border-zinc-700 min-h-[100px]"
                        placeholder="E.g., A friendly coding assistant that loves Python, checks on my projects every few hours, and sends me daily summaries..."
                      />
                    </div>
                    {soulError && (
                      <p className="text-red-400 text-xs">{soulError}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        onClick={generateSoulFromDescription}
                        disabled={soulGenerating || !soulDescription.trim()}
                        className="bg-gradient-to-r from-purple-600 to-pink-600"
                      >
                        {soulGenerating ? (
                          <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                        ) : (
                          <Sparkles className="w-4 h-4 mr-2" />
                        )}
                        Generate Soul
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulMode(null);
                          setSoulError("");
                        }}
                        className="border-zinc-700"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {/* Generate from Presets */}
                {soulMode === "pick" && !soulPreview && (
                  <div className="space-y-4">
                    <p className="text-sm text-zinc-400">
                      Pick which autonomous behaviors to enable:
                    </p>
                    <div>
                      <label className="text-xs text-zinc-500 mb-1 block">
                        Agent Name
                      </label>
                      <Input
                        value={soulAgentName}
                        onChange={(e) => setSoulAgentName(e.target.value)}
                        className="bg-zinc-800 border-zinc-700"
                        placeholder="UnClaude"
                      />
                    </div>
                    <div className="space-y-2">
                      {soulBehaviors.map((b) => (
                        <label
                          key={b.key}
                          className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all ${
                            selectedBehaviors.includes(b.key)
                              ? "bg-purple-600/20 border border-purple-500/30"
                              : "bg-zinc-800/50 border border-zinc-700/50 hover:border-zinc-600"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedBehaviors.includes(b.key)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedBehaviors([
                                  ...selectedBehaviors,
                                  b.key,
                                ]);
                              } else {
                                setSelectedBehaviors(
                                  selectedBehaviors.filter((k) => k !== b.key),
                                );
                              }
                            }}
                            className="rounded border-zinc-600"
                          />
                          <div className="flex-1">
                            <span className="text-sm font-medium">
                              {b.label}
                            </span>
                            <span className="text-xs text-zinc-500 ml-2">
                              every {b.interval}
                            </span>
                          </div>
                        </label>
                      ))}
                    </div>
                    {soulError && (
                      <p className="text-red-400 text-xs">{soulError}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        onClick={generateSoulFromPresets}
                        disabled={
                          soulGenerating || selectedBehaviors.length === 0
                        }
                        className="bg-gradient-to-r from-purple-600 to-pink-600"
                      >
                        {soulGenerating ? (
                          <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                        ) : (
                          <Sparkles className="w-4 h-4 mr-2" />
                        )}
                        Generate Soul
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulMode(null);
                          setSoulError("");
                        }}
                        className="border-zinc-700"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {/* Soul Preview (after generation) */}
                {soulPreview && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-sm text-zinc-400">
                      <Eye className="w-4 h-4" /> Preview generated soul:
                    </div>
                    <div className="p-4 bg-zinc-800/50 rounded-lg">
                      <pre className="text-xs text-zinc-300 whitespace-pre-wrap max-h-80 overflow-auto font-mono">
                        {soulPreview}
                      </pre>
                    </div>
                    {soulError && (
                      <p className="text-red-400 text-xs">{soulError}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        onClick={() => saveSoul(soulPreview)}
                        disabled={soulSaving}
                        className="bg-green-600 hover:bg-green-500"
                      >
                        {soulSaving ? (
                          <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                        ) : (
                          <Check className="w-4 h-4 mr-2" />
                        )}
                        Save This Soul
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulPreview(null);
                        }}
                        className="border-zinc-700"
                      >
                        Regenerate
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setSoulPreview(null);
                          setSoulMode(null);
                          setSoulError("");
                        }}
                        className="border-zinc-700"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Config Path */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-lg">
                  📁 Configuration Files
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-400">Config Path</span>
                  <code className="text-sm bg-zinc-800 px-3 py-1 rounded">
                    {settings.config_path || "~/.unclaude/config.yaml"}
                  </code>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Re-run Setup Wizard */}
          {onRunSetupWizard && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <Card className="bg-zinc-900/50 border-zinc-800 border-dashed">
                <CardContent className="py-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-zinc-300">
                        🧙 Setup Wizard
                      </p>
                      <p className="text-xs text-zinc-500 mt-1">
                        Re-run the guided setup to reconfigure provider,
                        messaging, soul, and daemon
                      </p>
                    </div>
                    <Button
                      onClick={onRunSetupWizard}
                      variant="outline"
                      className="border-blue-500/30 text-blue-400 hover:bg-blue-600/20"
                    >
                      <Play className="w-4 h-4 mr-2" /> Run Setup Wizard
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
