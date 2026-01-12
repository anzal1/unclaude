"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Zap, Play, XCircle, RefreshCw, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Job {
  job_id: string;
  task: string;
  status: "running" | "completed" | "failed" | "cancelled";
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [newTask, setNewTask] = useState("");

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadJobs = async () => {
    try {
      const res = await fetch("/api/jobs");
      const data = await res.json();
      setJobs(data.jobs || []);
    } catch (error) {
      console.error("Failed to load jobs:", error);
    } finally {
      setLoading(false);
    }
  };

  const createJob = async () => {
    if (!newTask.trim()) return;
    try {
      await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: newTask }),
      });
      setNewTask("");
      loadJobs();
    } catch (error) {
      alert("Failed to create job");
    }
  };

  const cancelJob = async (jobId: string) => {
    try {
      await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
      loadJobs();
    } catch (error) {
      alert("Failed to cancel job");
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "running": return <RefreshCw className="w-4 h-4 animate-spin text-yellow-400" />;
      case "completed": return <CheckCircle2 className="w-4 h-4 text-green-400" />;
      case "failed": return <AlertCircle className="w-4 h-4 text-red-400" />;
      default: return <Clock className="w-4 h-4 text-zinc-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running": return "bg-yellow-500";
      case "completed": return "bg-green-500";
      case "failed": return "bg-red-500";
      default: return "bg-zinc-500";
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span className="text-2xl">⚡</span> Background Jobs
        </h1>
        <p className="text-sm text-zinc-400 mt-1">Monitor running tasks</p>
      </div>

      <ScrollArea className="flex-1 overflow-auto" style={{ height: 'calc(100vh - 100px)' }}>
        <div className="px-6 py-6">
        {/* New Job */}
        <div className="flex gap-2 mb-6">
          <Input
            placeholder="Enter a task to run in the background..."
            value={newTask}
            onChange={(e) => setNewTask(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createJob()}
            className="flex-1 bg-zinc-800 border-zinc-700"
          />
          <Button onClick={createJob} className="bg-gradient-to-r from-blue-600 to-purple-600">
            <Play className="w-4 h-4 mr-2" />
            Start Job
          </Button>
        </div>

        {/* Jobs List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <RefreshCw className="w-6 h-6 animate-spin text-zinc-500" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ repeat: Infinity, duration: 2 }}
              className="text-6xl mb-4"
            >
              ⚡
            </motion.div>
            <h3 className="text-lg font-medium text-zinc-300">No background jobs</h3>
            <p className="text-sm text-zinc-500 mt-2">
              Start a background task to see it here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job, i) => (
              <motion.div
                key={job.job_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Card className="bg-zinc-900/50 border-zinc-800 hover:border-zinc-700 transition-colors">
                  <CardContent className="p-4">
                    <div className="flex items-start gap-4">
                      <div className={`w-3 h-3 rounded-full mt-1 ${getStatusColor(job.status)} ${job.status === "running" ? "animate-pulse" : ""}`} />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{job.task}</p>
                        <div className="flex items-center gap-3 mt-2 text-xs text-zinc-500">
                          {getStatusIcon(job.status)}
                          <span className="capitalize">{job.status}</span>
                          <span>•</span>
                          <span>
                            Started: {job.started_at?.split("T")[1]?.split(".")[0] || "Unknown"}
                          </span>
                          {job.error && (
                            <>
                              <span>•</span>
                              <span className="text-red-400">{job.error}</span>
                            </>
                          )}
                        </div>
                      </div>
                      {job.status === "running" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelJob(job.job_id)}
                          className="text-red-400 hover:text-red-300 hover:bg-red-950/30"
                        >
                          <XCircle className="w-4 h-4" />
                        </Button>
                      )}
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
