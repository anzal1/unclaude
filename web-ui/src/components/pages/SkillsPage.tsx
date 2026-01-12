"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Target, Plus, Play, RefreshCw, ChevronRight, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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

interface Skill {
  name: string;
  description: string;
  steps: number;
  steps_preview: string[];
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [newSkillName, setNewSkillName] = useState("");
  const [newSkillDesc, setNewSkillDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [runningSkill, setRunningSkill] = useState<string | null>(null);
  const [skillResult, setSkillResult] = useState<string | null>(null);
  const [resultDialogOpen, setResultDialogOpen] = useState(false);

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/skills");
      const data = await res.json();
      setSkills(data.skills || []);
    } catch (err) {
      console.error("Failed to load skills:", err);
    } finally {
      setLoading(false);
    }
  };

  const createSkill = async () => {
    if (!newSkillName.trim()) return;

    setCreating(true);
    try {
      const res = await fetch("/api/skills/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newSkillName.trim(),
          description: newSkillDesc.trim(),
        }),
      });
      const data = await res.json();

      if (data.success) {
        setNewSkillName("");
        setNewSkillDesc("");
        setDialogOpen(false);
        loadSkills();
      } else {
        alert(data.message || "Failed to create skill");
      }
    } catch (err) {
      console.error("Failed to create skill:", err);
    } finally {
      setCreating(false);
    }
  };

  const runSkill = async (name: string) => {
    setRunningSkill(name);
    try {
      const res = await fetch(`/api/skills/${name}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();

      if (data.success) {
        setSkillResult(data.response);
        setResultDialogOpen(true);
      } else {
        alert("Failed to run skill: " + (data.detail || "Unknown error"));
      }
    } catch (err) {
      console.error("Failed to run skill:", err);
    } finally {
      setRunningSkill(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <Target className="w-6 h-6 text-orange-400" />
              Skills
            </h1>
            <p className="text-sm text-zinc-400 mt-1">
              Reusable workflows and automation sequences
            </p>
          </div>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-gradient-to-r from-orange-600 to-amber-600">
                <Plus className="w-4 h-4 mr-2" />
                New Skill
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle>Create New Skill</DialogTitle>
                <DialogDescription>
                  Create a reusable workflow that can be triggered on demand.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-zinc-400 mb-1 block">Name</label>
                  <Input
                    placeholder="deploy-to-staging"
                    value={newSkillName}
                    onChange={(e) => setNewSkillName(e.target.value)}
                    className="bg-zinc-800 border-zinc-700"
                  />
                </div>
                <div>
                  <label className="text-sm text-zinc-400 mb-1 block">Description</label>
                  <Textarea
                    placeholder="Deploy the application to staging environment"
                    value={newSkillDesc}
                    onChange={(e) => setNewSkillDesc(e.target.value)}
                    className="bg-zinc-800 border-zinc-700"
                    rows={3}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={createSkill}
                  disabled={!newSkillName.trim() || creating}
                  className="bg-orange-600 hover:bg-orange-500"
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
          ) : skills.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-center py-16"
            >
              <Zap className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
              <h3 className="text-lg font-medium mb-2">No Skills Configured</h3>
              <p className="text-zinc-500 mb-6 max-w-md mx-auto">
                Skills are reusable workflows defined in UNCLAUDE.md or ~/.unclaude/skills/.
                Create your first skill to automate repetitive tasks.
              </p>
              <Button
                variant="outline"
                onClick={() => setDialogOpen(true)}
              >
                <Plus className="w-4 h-4 mr-2" />
                Create Skill
              </Button>
            </motion.div>
          ) : (
            <div className="grid gap-4">
              {skills.map((skill, i) => (
                <motion.div
                  key={skill.name}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <Card className="bg-zinc-900/50 border-zinc-800 hover:border-zinc-700 transition-colors">
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-4">
                          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-amber-500/20 flex items-center justify-center">
                            <Target className="w-6 h-6 text-orange-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-lg">{skill.name}</h3>
                            <p className="text-sm text-zinc-500">
                              {skill.description || "No description"}
                            </p>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => runSkill(skill.name)}
                          disabled={runningSkill === skill.name}
                          className="bg-orange-600 hover:bg-orange-500"
                        >
                          {runningSkill === skill.name ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <>
                              <Play className="w-4 h-4 mr-1" />
                              Run
                            </>
                          )}
                        </Button>
                      </div>
                      <div className="mt-4">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge variant="secondary">{skill.steps} steps</Badge>
                        </div>
                        {skill.steps_preview.length > 0 && (
                          <div className="flex items-center gap-2 text-xs text-zinc-500">
                            {skill.steps_preview.map((step, j) => (
                              <span key={j} className="flex items-center gap-1">
                                {j > 0 && <ChevronRight className="w-3 h-3" />}
                                {step}
                              </span>
                            ))}
                            {skill.steps > 3 && <span>...</span>}
                          </div>
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

      {/* Result Dialog */}
      <Dialog open={resultDialogOpen} onOpenChange={setResultDialogOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800 max-w-2xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle>Skill Result</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            <pre className="text-sm bg-zinc-800 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap">
              {skillResult}
            </pre>
          </ScrollArea>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResultDialogOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
