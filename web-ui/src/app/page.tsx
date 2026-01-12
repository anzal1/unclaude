"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  MessageSquare, 
  Brain, 
  Zap, 
  Settings as SettingsIcon,
  Menu,
  X,
  Loader2,
  Wand2,
  Target,
  Plug
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

import ChatPage from "@/components/pages/ChatPage";
import MemoryPage from "@/components/pages/MemoryPage";
import JobsPage from "@/components/pages/JobsPage";
import SettingsPage from "@/components/pages/SettingsPage";
import RalphPage from "@/components/pages/RalphPage";
import PluginsPage from "@/components/pages/PluginsPage";
import SkillsPage from "@/components/pages/SkillsPage";
import Onboarding from "@/components/Onboarding";

const pages = [
  { id: "chat", name: "Chat", icon: MessageSquare, component: ChatPage },
  { id: "memory", name: "Memory", icon: Brain, component: MemoryPage },
  { id: "ralph", name: "Ralph Mode", icon: Wand2, component: RalphPage },
  { id: "jobs", name: "Jobs", icon: Zap, component: JobsPage },
  { id: "skills", name: "Skills", icon: Target, component: SkillsPage },
  { id: "plugins", name: "Plugins", icon: Plug, component: PluginsPage },
  { id: "settings", name: "Settings", icon: SettingsIcon, component: SettingsPage },
];

export default function Dashboard() {
  const [currentPage, setCurrentPage] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showOnboarding, setShowOnboarding] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  // Check if onboarding is needed
  useEffect(() => {
    const checkOnboarding = async () => {
      try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        
        // Check if any provider has a key configured
        const hasAnyKey = Object.values(data.providers || {}).some(
          (p: any) => p.has_key
        );
        
        setShowOnboarding(!hasAnyKey);
      } catch {
        // If API fails, show dashboard anyway
        setShowOnboarding(false);
      } finally {
        setLoading(false);
      }
    };
    
    checkOnboarding();
  }, []);

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  // Show onboarding if needed
  if (showOnboarding) {
    return <Onboarding onComplete={handleOnboardingComplete} />;
  }

  const CurrentPageComponent = pages.find(p => p.id === currentPage)?.component || ChatPage;

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: sidebarOpen ? 280 : 80 }}
        className="relative flex flex-col border-r border-zinc-800 bg-zinc-900/50 backdrop-blur-xl"
      >
        {/* Logo */}
        <div className="flex items-center gap-3 p-6 border-b border-zinc-800">
          <motion.div 
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-purple-500 to-cyan-500"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <span className="text-lg">🤖</span>
          </motion.div>
          <AnimatePresence>
            {sidebarOpen && (
              <motion.span
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="text-xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent"
              >
                UnClaude
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Nav */}
        <ScrollArea className="flex-1 py-4">
          <nav className="space-y-1 px-3">
            {pages.map((page) => (
              <motion.button
                key={page.id}
                onClick={() => setCurrentPage(page.id)}
                whileHover={{ x: 4 }}
                whileTap={{ scale: 0.98 }}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors",
                  currentPage === page.id
                    ? "bg-gradient-to-r from-blue-600/20 to-purple-600/20 text-white border border-blue-500/30"
                    : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
                )}
              >
                <page.icon className="h-5 w-5 flex-shrink-0" />
                <AnimatePresence>
                  {sidebarOpen && (
                    <motion.span
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -10 }}
                    >
                      {page.name}
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            ))}
          </nav>
        </ScrollArea>

        {/* Footer */}
        <div className="border-t border-zinc-800 p-4">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            <AnimatePresence>
              {sidebarOpen && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  v0.2.0 • Local Mode
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Toggle */}
        <Button
          variant="ghost"
          size="icon"
          className="absolute -right-3 top-20 h-6 w-6 rounded-full border border-zinc-800 bg-zinc-900"
          onClick={() => setSidebarOpen(!sidebarOpen)}
        >
          {sidebarOpen ? <X className="h-3 w-3" /> : <Menu className="h-3 w-3" />}
        </Button>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentPage}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            <CurrentPageComponent />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
