"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Brain, Search, Trash2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Memory {
  id: string;
  content: string;
  memory_type: string;
  project_path: string | null;
  created_at: string | null;
}

interface Stats {
  total: number;
  by_type?: Record<string, number>;
}

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [stats, setStats] = useState<Stats>({ total: 0 });
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    loadMemories();
    loadStats();
  }, []);

  const loadMemories = async () => {
    try {
      const params = searchQuery ? `?query=${encodeURIComponent(searchQuery)}` : "";
      const res = await fetch(`/api/memories${params}`);
      const data = await res.json();
      setMemories(data.memories || []);
    } catch (error) {
      console.error("Failed to load memories:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const res = await fetch("/api/memories/stats");
      const data = await res.json();
      setStats(data);
    } catch (error) {
      console.error("Failed to load stats:", error);
    }
  };

  const deleteMemory = async (id: string) => {
    if (!confirm("Delete this memory?")) return;
    try {
      await fetch(`/api/memories/${id}`, { method: "DELETE" });
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch (error) {
      alert("Failed to delete memory");
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span className="text-2xl">🧠</span> Memory
        </h1>
        <p className="text-sm text-zinc-400 mt-1">Browse and manage stored memories</p>
      </div>

      <ScrollArea className="flex-1 overflow-auto" style={{ height: 'calc(100vh - 100px)' }}>
        <div className="px-6 py-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {[
            { label: "Total Memories", value: stats.total, color: "blue" },
            { label: "Core Memories", value: stats.by_type?.core || 0, color: "purple" },
            { label: "Recall Memories", value: stats.by_type?.recall || 0, color: "cyan" },
          ].map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <Card className="bg-zinc-900/50 border-zinc-800">
                <CardContent className="p-4 text-center">
                  <p className={`text-3xl font-bold bg-gradient-to-r from-${stat.color}-400 to-${stat.color}-600 bg-clip-text text-transparent`}>
                    {stat.value}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">{stat.label}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Search */}
        <div className="flex gap-2 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <Input
              placeholder="Search memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && loadMemories()}
              className="pl-10 bg-zinc-800 border-zinc-700"
            />
          </div>
          <Button onClick={loadMemories} variant="secondary">
            <RefreshCw className="w-4 h-4 mr-2" />
            Search
          </Button>
        </div>

        {/* Memories */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="w-6 h-6 animate-spin text-zinc-500" />
          </div>
        ) : memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ repeat: Infinity, duration: 2 }}
              className="text-6xl mb-4"
            >
              🧠
            </motion.div>
            <h3 className="text-lg font-medium text-zinc-300">No memories yet</h3>
            <p className="text-sm text-zinc-500 mt-2">
              Memories are created as you chat with UnClaude.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {memories.map((mem, i) => (
              <motion.div
                key={mem.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Card className="bg-zinc-900/50 border-zinc-800 hover:border-zinc-700 transition-colors">
                  <CardContent className="p-4">
                    <p className="text-sm text-zinc-200 mb-3">{mem.content}</p>
                    <div className="flex items-center gap-3 flex-wrap">
                      <Badge variant={mem.memory_type === "core" ? "default" : "secondary"}>
                        {mem.memory_type}
                      </Badge>
                      <span className="text-xs text-zinc-500">
                        {mem.project_path || "Global"}
                      </span>
                      <span className="text-xs text-zinc-500">
                        {mem.created_at?.split("T")[0] || "Unknown"}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => deleteMemory(mem.id)}
                        className="ml-auto text-red-400 hover:text-red-300 hover:bg-red-950/30"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
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
