"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Plug, Plus, RefreshCw, ExternalLink, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

interface Plugin {
  name: string;
  version: string;
  description: string;
  tools_count: number;
  hooks_count: number;
}

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [pluginsDir, setPluginsDir] = useState("");
  const [loading, setLoading] = useState(true);
  const [newPluginName, setNewPluginName] = useState("");
  const [creating, setCreating] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    loadPlugins();
  }, []);

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/plugins");
      const data = await res.json();
      setPlugins(data.plugins || []);
      setPluginsDir(data.plugins_dir || "");
    } catch (err) {
      console.error("Failed to load plugins:", err);
    } finally {
      setLoading(false);
    }
  };

  const createPlugin = async () => {
    if (!newPluginName.trim()) return;

    setCreating(true);
    try {
      const res = await fetch("/api/plugins/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newPluginName.trim() }),
      });
      const data = await res.json();

      if (data.success) {
        setNewPluginName("");
        setDialogOpen(false);
        loadPlugins();
      } else {
        alert(data.message || "Failed to create plugin");
      }
    } catch (err) {
      console.error("Failed to create plugin:", err);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <Plug className="w-6 h-6 text-green-400" />
              Plugins
            </h1>
            <p className="text-sm text-zinc-400 mt-1">
              Extend UnClaude with custom tools and hooks
            </p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-gradient-to-r from-green-600 to-emerald-600">
                <Plus className="w-4 h-4 mr-2" />
                New Plugin
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle>Create New Plugin</DialogTitle>
                <DialogDescription>
                  Enter a name for your new plugin. A template will be created with example tools and hooks.
                </DialogDescription>
              </DialogHeader>
              <Input
                placeholder="my-plugin"
                value={newPluginName}
                onChange={(e) => setNewPluginName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createPlugin()}
                className="bg-zinc-800 border-zinc-700"
              />
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={createPlugin}
                  disabled={!newPluginName.trim() || creating}
                  className="bg-green-600 hover:bg-green-500"
                >
                  {creating ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <ScrollArea className="flex-1 overflow-auto" style={{ height: 'calc(100vh - 100px)' }}>
        <div className="max-w-4xl mx-auto px-6 py-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-6 h-6 animate-spin text-zinc-500" />
            </div>
          ) : plugins.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center py-16"
            >
              <Package className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
              <h3 className="text-lg font-medium mb-2">No Plugins Installed</h3>
              <p className="text-zinc-500 mb-6 max-w-md mx-auto">
                Plugins let you extend UnClaude with custom tools, hooks, and integrations.
                Create your first plugin to get started.
              </p>
              <div className="text-sm text-zinc-600">
                Plugins directory: <code className="bg-zinc-800 px-2 py-1 rounded">{pluginsDir}</code>
              </div>
            </motion.div>
          ) : (
            <div className="grid gap-4">
              {plugins.map((plugin, i) => (
                <motion.div
                  key={plugin.name}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <Card className="bg-zinc-900/50 border-zinc-800 hover:border-zinc-700 transition-colors">
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-green-500/20 to-emerald-500/20 flex items-center justify-center">
                            <Plug className="w-6 h-6 text-green-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-lg">{plugin.name}</h3>
                            <p className="text-sm text-zinc-500">
                              {plugin.description || "No description"}
                            </p>
                          </div>
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          v{plugin.version}
                        </Badge>
                      </div>
                      <div className="mt-4 flex items-center gap-4">
                        <div className="flex items-center gap-2 text-sm text-zinc-400">
                          <span className="w-2 h-2 rounded-full bg-blue-500" />
                          {plugin.tools_count} tools
                        </div>
                        <div className="flex items-center gap-2 text-sm text-zinc-400">
                          <span className="w-2 h-2 rounded-full bg-purple-500" />
                          {plugin.hooks_count} hooks
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
