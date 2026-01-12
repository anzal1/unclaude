"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Wand2, Play, Square, Clock, CheckCircle, XCircle, AlertCircle, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";

interface RalphJob {
  id: string;
  task: string;
  status: "starting" | "running" | "completed" | "failed" | "stopped";
  started_at: string;
  current_iteration: number;
  max_iterations: number;
  max_cost: number;
  result?: {
    success: boolean;
    iterations: number;
    total_cost: number;
    error?: string;
  };
  error?: string;
}

export default function RalphPage() {
  const [task, setTask] = useState("");
  const [maxIterations, setMaxIterations] = useState(50);
  const [maxCost, setMaxCost] = useState(10.0);
  const [feedbackCommands, setFeedbackCommands] = useState("npm test");
  const [jobs, setJobs] = useState<RalphJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  const loadJobs = async () => {
    try {
      const res = await fetch("/api/ralph/jobs");
      const data = await res.json();
      setJobs(data.jobs || []);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    }
  };

  const startRalph = async () => {
    if (!task.trim()) return;
    
    setStarting(true);
    try {
      const res = await fetch("/api/ralph/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task: task.trim(),
          max_iterations: maxIterations,
          max_cost: maxCost,
          feedback_commands: feedbackCommands.split("\n").map(c => c.trim()).filter(Boolean),
        }),
      });
      const data = await res.json();
      
      if (data.success) {
        setTask("");
        loadJobs();
      }
    } catch (err) {
      console.error("Failed to start Ralph:", err);
    } finally {
      setStarting(false);
    }
  };

  const stopJob = async (jobId: string) => {
    try {
      await fetch(`/api/ralph/stop/${jobId}`, { method: "POST" });
      loadJobs();
    } catch (err) {
      console.error("Failed to stop job:", err);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "running":
      case "starting":
        return <RefreshCw className="w-4 h-4 animate-spin text-blue-400" />;
      case "completed":
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-red-400" />;
      case "stopped":
        return <AlertCircle className="w-4 h-4 text-yellow-400" />;
      default:
        return <Clock className="w-4 h-4 text-zinc-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
      case "starting":
        return "bg-blue-600/20 text-blue-400 border-blue-600/30";
      case "completed":
        return "bg-green-600/20 text-green-400 border-green-600/30";
      case "failed":
        return "bg-red-600/20 text-red-400 border-red-600/30";
      case "stopped":
        return "bg-yellow-600/20 text-yellow-400 border-yellow-600/30";
      default:
        return "bg-zinc-600/20 text-zinc-400 border-zinc-600/30";
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Wand2 className="w-6 h-6 text-purple-400" />
          Ralph Wiggum Mode
        </h1>
        <p className="text-sm text-zinc-400 mt-1">
          Autonomous task completion with test/lint feedback loops
        </p>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* Left: New Task Form */}
        <div className="w-1/2 border-r border-zinc-800 p-6">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader>
                <CardTitle className="text-lg">🚀 New Autonomous Task</CardTitle>
                <CardDescription>
                  Ralph will iterate until the task is complete or limits are reached
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-sm text-zinc-400 mb-2 block">Task Description</label>
                  <Textarea
                    placeholder="Describe what you want Ralph to accomplish..."
                    value={task}
                    onChange={(e) => setTask(e.target.value)}
                    className="bg-zinc-800 border-zinc-700 min-h-24"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-zinc-400 mb-2 block">
                      Max Iterations: {maxIterations}
                    </label>
                    <Slider
                      value={[maxIterations]}
                      onValueChange={(v) => setMaxIterations(v[0])}
                      min={5}
                      max={100}
                      step={5}
                      className="py-2"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-zinc-400 mb-2 block">
                      Max Cost: ${maxCost.toFixed(2)}
                    </label>
                    <Slider
                      value={[maxCost]}
                      onValueChange={(v) => setMaxCost(v[0])}
                      min={1}
                      max={50}
                      step={1}
                      className="py-2"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-sm text-zinc-400 mb-2 block">
                    Feedback Commands (one per line)
                  </label>
                  <Textarea
                    placeholder="npm test&#10;npm run lint"
                    value={feedbackCommands}
                    onChange={(e) => setFeedbackCommands(e.target.value)}
                    className="bg-zinc-800 border-zinc-700 font-mono text-sm"
                    rows={3}
                  />
                </div>

                <Button
                  onClick={startRalph}
                  disabled={!task.trim() || starting}
                  className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 h-12"
                >
                  {starting ? (
                    <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Play className="w-4 h-4 mr-2" />
                  )}
                  Start Ralph Mode
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Right: Jobs List */}
        <div className="w-1/2 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Recent Jobs</h2>
            <Button variant="ghost" size="sm" onClick={loadJobs}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>

          <ScrollArea className="h-[calc(100vh-220px)]">
            <div className="space-y-3 pr-4">
              {jobs.length === 0 ? (
                <div className="text-center py-12 text-zinc-500">
                  <Wand2 className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No Ralph jobs yet</p>
                  <p className="text-sm">Start a new task to see it here</p>
                </div>
              ) : (
                jobs.map((job) => (
                  <motion.div
                    key={job.id}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                  >
                    <Card className="bg-zinc-900/50 border-zinc-800">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            {getStatusIcon(job.status)}
                            <Badge className={getStatusColor(job.status)}>
                              {job.status}
                            </Badge>
                            <span className="text-xs text-zinc-500">#{job.id}</span>
                          </div>
                          {(job.status === "running" || job.status === "starting") && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => stopJob(job.id)}
                              className="h-7"
                            >
                              <Square className="w-3 h-3 mr-1" />
                              Stop
                            </Button>
                          )}
                        </div>
                        <p className="text-sm text-zinc-300 mb-2 line-clamp-2">
                          {job.task}
                        </p>
                        <div className="flex items-center gap-4 text-xs text-zinc-500">
                          <span>Started: {new Date(job.started_at).toLocaleTimeString()}</span>
                          {job.result && (
                            <>
                              <span>Iterations: {job.result.iterations}</span>
                              <span>Cost: ${job.result.total_cost.toFixed(2)}</span>
                            </>
                          )}
                        </div>
                        {job.error && (
                          <p className="text-xs text-red-400 mt-2">{job.error}</p>
                        )}
                      </CardContent>
                    </Card>
                  </motion.div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
