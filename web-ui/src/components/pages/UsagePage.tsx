"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart3,
  TrendingUp,
  DollarSign,
  Zap,
  AlertTriangle,
  Download,
  RefreshCw,
  Calendar,
  Cpu,
  Shield,
  Trash2,
  Save,
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
import { Slider } from "@/components/ui/slider";

// ── Types ──────────────────────────────────────────────

interface UsageSummary {
  period: string;
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_tokens_per_request: number;
  unique_models: number;
  period_start: string;
  period_end: string;
}

interface DailyBreakdown {
  date: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  models: string[];
}

interface ModelBreakdown {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  avg_tokens: number;
}

interface UsageRecord {
  id: number;
  timestamp: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  session_id: string | null;
  task_id: string | null;
  request_type: string;
}

interface BudgetStatus {
  has_budget: boolean;
  limit_usd: number;
  period: string;
  action: string;
  soft_limit_pct: number;
  current_spend: number;
  remaining: number;
  utilization_pct: number;
  status: string;
}

// ── Stat Card ──────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color,
  delay = 0,
}: {
  icon: any;
  label: string;
  value: string;
  sub?: string;
  color: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
    >
      <Card className="bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 transition-colors">
        <CardContent className="p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-lg ${color}`}>
              <Icon className="h-4 w-4 text-white" />
            </div>
            <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
              {label}
            </span>
          </div>
          <p className="text-2xl font-bold text-white">{value}</p>
          {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// ── Bar Chart (simple CSS) ─────────────────────────────

function MiniBarChart({
  data,
  maxVal,
}: {
  data: { label: string; value: number; color?: string }[];
  maxVal: number;
}) {
  return (
    <div className="space-y-2">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-3">
          <span className="text-xs text-zinc-400 w-20 truncate text-right">
            {d.label}
          </span>
          <div className="flex-1 h-5 bg-zinc-800 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{
                width: maxVal > 0 ? `${(d.value / maxVal) * 100}%` : "0%",
              }}
              transition={{ delay: i * 0.05, duration: 0.5 }}
              className={`h-full rounded-full ${d.color || "bg-blue-500"}`}
            />
          </div>
          <span className="text-xs text-zinc-400 w-16 text-right">
            ${d.value.toFixed(4)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Budget Ring ────────────────────────────────────────

function BudgetRing({ pct, status }: { pct: number; status: string }) {
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset =
    circumference - (Math.min(pct, 100) / 100) * circumference;
  const color =
    status === "blocked"
      ? "#ef4444"
      : status === "over_budget"
        ? "#f97316"
        : status === "warning"
          ? "#eab308"
          : "#22c55e";

  return (
    <div className="relative w-28 h-28">
      <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke="#27272a"
          strokeWidth="8"
        />
        <motion.circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold text-white">{pct.toFixed(0)}%</span>
        <span className="text-[10px] text-zinc-400">used</span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════
// ██  USAGE PAGE
// ══════════════════════════════════════════════════════

export default function UsagePage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [daily, setDaily] = useState<DailyBreakdown[]>([]);
  const [models, setModels] = useState<ModelBreakdown[]>([]);
  const [recent, setRecent] = useState<UsageRecord[]>([]);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState("today");
  const [refreshing, setRefreshing] = useState(false);

  // Budget form
  const [budgetLimit, setBudgetLimit] = useState("5.00");
  const [budgetPeriod, setBudgetPeriod] = useState("daily");
  const [budgetAction, setBudgetAction] = useState("warn");
  const [budgetSoftPct, setBudgetSoftPct] = useState([80]);
  const [savingBudget, setSavingBudget] = useState(false);

  // ── Data Loading ─────────────────────────────────────

  const loadAll = useCallback(async () => {
    try {
      const [sumRes, dailyRes, modelsRes, recentRes, budgetRes] =
        await Promise.all([
          fetch(`/api/usage/summary?period=${period}`),
          fetch("/api/usage/daily?days=14"),
          fetch(`/api/usage/models?period=${period}`),
          fetch("/api/usage/recent?limit=30"),
          fetch("/api/usage/budget"),
        ]);

      const [sumData, dailyData, modelsData, recentData, budgetData] =
        await Promise.all([
          sumRes.json(),
          dailyRes.json(),
          modelsRes.json(),
          recentRes.json(),
          budgetRes.json(),
        ]);

      setSummary(sumData);
      setDaily(dailyData.days || []);
      setModels(modelsData.models || []);
      setRecent(recentData.records || []);
      setBudget(budgetData);
    } catch (err) {
      console.error("Failed to load usage data:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period]);

  useEffect(() => {
    setLoading(true);
    loadAll();
  }, [loadAll]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => loadAll(), 30000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadAll();
  };

  // ── Budget Actions ───────────────────────────────────

  const saveBudget = async () => {
    setSavingBudget(true);
    try {
      await fetch("/api/usage/budget", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          limit_usd: parseFloat(budgetLimit),
          period: budgetPeriod,
          action: budgetAction,
          soft_limit_pct: budgetSoftPct[0] / 100,
        }),
      });
      loadAll();
    } catch (err) {
      console.error("Failed to save budget:", err);
    } finally {
      setSavingBudget(false);
    }
  };

  const clearBudget = async () => {
    try {
      await fetch("/api/usage/budget", { method: "DELETE" });
      loadAll();
    } catch (err) {
      console.error("Failed to clear budget:", err);
    }
  };

  const exportCSV = () => {
    window.open("/api/usage/export", "_blank");
  };

  // ── Format Helpers ───────────────────────────────────

  const fmtCost = (usd: number) =>
    usd >= 1 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(4)}`;

  const fmtTokens = (n: number) =>
    n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(1)}M`
      : n >= 1_000
        ? `${(n / 1_000).toFixed(1)}K`
        : String(n);

  const fmtTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  // ── Render ───────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
      </div>
    );
  }

  const maxDailyCost = Math.max(...daily.map((d) => d.cost_usd), 0.0001);
  const maxModelCost = Math.max(...models.map((m) => m.cost_usd), 0.0001);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-xl px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span className="text-2xl">📊</span> Usage & Costs
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Token usage, spend tracking, and budget management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-[130px] bg-zinc-800 border-zinc-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Today</SelectItem>
              <SelectItem value="yesterday">Yesterday</SelectItem>
              <SelectItem value="week">This Week</SelectItem>
              <SelectItem value="month">This Month</SelectItem>
              <SelectItem value="all">All Time</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={handleRefresh}
            className="border-zinc-700"
          >
            <RefreshCw
              className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
            />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={exportCSV}
            className="border-zinc-700 gap-1"
          >
            <Download className="h-3 w-3" /> CSV
          </Button>
        </div>
      </div>

      {/* Body */}
      <ScrollArea className="flex-1" style={{ height: "calc(100vh - 100px)" }}>
        <div className="p-6 space-y-6 max-w-6xl mx-auto">
          {/* ── Stats Row ─────────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={DollarSign}
              label="Total Spend"
              value={fmtCost(summary?.total_cost_usd ?? 0)}
              sub={`${period} period`}
              color="bg-green-600"
              delay={0}
            />
            <StatCard
              icon={Zap}
              label="Requests"
              value={String(summary?.total_requests ?? 0)}
              sub={`${summary?.unique_models ?? 0} model${(summary?.unique_models ?? 0) !== 1 ? "s" : ""}`}
              color="bg-blue-600"
              delay={0.05}
            />
            <StatCard
              icon={TrendingUp}
              label="Total Tokens"
              value={fmtTokens(summary?.total_tokens ?? 0)}
              sub={`${fmtTokens(summary?.total_input_tokens ?? 0)} in / ${fmtTokens(summary?.total_output_tokens ?? 0)} out`}
              color="bg-purple-600"
              delay={0.1}
            />
            <StatCard
              icon={BarChart3}
              label="Avg / Request"
              value={fmtTokens(summary?.avg_tokens_per_request ?? 0)}
              sub="tokens per call"
              color="bg-orange-600"
              delay={0.15}
            />
          </div>

          {/* ── Budget + Models Row ───────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Budget Card */}
            <Card className="bg-zinc-900/60 border-zinc-800 lg:col-span-1">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Shield className="h-4 w-4 text-yellow-500" /> Budget
                </CardTitle>
                <CardDescription>Set spending limits</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {budget?.has_budget ? (
                  <div className="flex flex-col items-center gap-3">
                    <BudgetRing
                      pct={budget.utilization_pct}
                      status={budget.status}
                    />
                    <div className="text-center space-y-1">
                      <p className="text-sm text-white">
                        {fmtCost(budget.current_spend)} /{" "}
                        {fmtCost(budget.limit_usd)}
                      </p>
                      <p className="text-xs text-zinc-400">
                        {fmtCost(budget.remaining)} remaining
                      </p>
                      <Badge
                        variant={
                          budget.status === "ok"
                            ? "secondary"
                            : budget.status === "warning"
                              ? "outline"
                              : "destructive"
                        }
                        className="text-[10px]"
                      >
                        {budget.period} • {budget.action}
                      </Badge>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={clearBudget}
                      className="text-red-400 hover:text-red-300 mt-1"
                    >
                      <Trash2 className="h-3 w-3 mr-1" /> Remove
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-zinc-400 mb-1 block">
                        Limit (USD)
                      </label>
                      <Input
                        type="number"
                        step="0.50"
                        min="0.01"
                        value={budgetLimit}
                        onChange={(e) => setBudgetLimit(e.target.value)}
                        className="bg-zinc-800 border-zinc-700"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-xs text-zinc-400 mb-1 block">
                          Period
                        </label>
                        <Select
                          value={budgetPeriod}
                          onValueChange={setBudgetPeriod}
                        >
                          <SelectTrigger className="bg-zinc-800 border-zinc-700 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="daily">Daily</SelectItem>
                            <SelectItem value="weekly">Weekly</SelectItem>
                            <SelectItem value="monthly">Monthly</SelectItem>
                            <SelectItem value="total">Total</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <label className="text-xs text-zinc-400 mb-1 block">
                          Action
                        </label>
                        <Select
                          value={budgetAction}
                          onValueChange={setBudgetAction}
                        >
                          <SelectTrigger className="bg-zinc-800 border-zinc-700 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="warn">Warn</SelectItem>
                            <SelectItem value="block">Block</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-zinc-400 mb-1 block">
                        Soft warning at {budgetSoftPct[0]}%
                      </label>
                      <Slider
                        value={budgetSoftPct}
                        onValueChange={setBudgetSoftPct}
                        min={50}
                        max={100}
                        step={5}
                        className="mt-2"
                      />
                    </div>
                    <Button
                      onClick={saveBudget}
                      disabled={savingBudget}
                      className="w-full bg-blue-600 hover:bg-blue-700"
                      size="sm"
                    >
                      <Save className="h-3 w-3 mr-1" />
                      {savingBudget ? "Saving..." : "Set Budget"}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Models Breakdown */}
            <Card className="bg-zinc-900/60 border-zinc-800 lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-purple-500" /> Cost by Model
                </CardTitle>
                <CardDescription>
                  {models.length} model{models.length !== 1 ? "s" : ""} used
                </CardDescription>
              </CardHeader>
              <CardContent>
                {models.length === 0 ? (
                  <p className="text-sm text-zinc-500 text-center py-6">
                    No usage data yet
                  </p>
                ) : (
                  <MiniBarChart
                    data={models.map((m, i) => ({
                      label: m.model.split("/").pop() || m.model,
                      value: m.cost_usd,
                      color: [
                        "bg-blue-500",
                        "bg-purple-500",
                        "bg-cyan-500",
                        "bg-green-500",
                        "bg-orange-500",
                        "bg-pink-500",
                      ][i % 6],
                    }))}
                    maxVal={maxModelCost}
                  />
                )}
              </CardContent>
            </Card>
          </div>

          {/* ── Daily Trend ───────────────────────── */}
          <Card className="bg-zinc-900/60 border-zinc-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Calendar className="h-4 w-4 text-blue-500" /> Daily Trend
              </CardTitle>
              <CardDescription>
                Cost per day over the last 14 days
              </CardDescription>
            </CardHeader>
            <CardContent>
              {daily.length === 0 ? (
                <p className="text-sm text-zinc-500 text-center py-6">
                  No data yet
                </p>
              ) : (
                <div className="flex items-end gap-1 h-36">
                  {daily.map((d, i) => {
                    const h =
                      maxDailyCost > 0 ? (d.cost_usd / maxDailyCost) * 100 : 0;
                    return (
                      <div
                        key={d.date}
                        className="flex-1 flex flex-col items-center gap-1 group relative"
                      >
                        {/* Tooltip */}
                        <div className="absolute -top-16 left-1/2 -translate-x-1/2 hidden group-hover:block bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs z-10 whitespace-nowrap">
                          <p className="text-white font-medium">{d.date}</p>
                          <p className="text-zinc-400">
                            {d.requests} req · {fmtTokens(d.total_tokens)} tok
                          </p>
                          <p className="text-green-400">
                            {fmtCost(d.cost_usd)}
                          </p>
                        </div>
                        <motion.div
                          initial={{ height: 0 }}
                          animate={{ height: `${Math.max(h, 2)}%` }}
                          transition={{ delay: i * 0.03, duration: 0.4 }}
                          className="w-full rounded-t bg-gradient-to-t from-blue-600 to-blue-400 min-h-[2px] cursor-pointer hover:from-blue-500 hover:to-blue-300"
                        />
                        <span className="text-[9px] text-zinc-500 hidden md:block">
                          {d.date.slice(5)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Recent Requests ───────────────────── */}
          <Card className="bg-zinc-900/60 border-zinc-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4 text-orange-500" /> Recent Requests
              </CardTitle>
              <CardDescription>Last 30 API calls</CardDescription>
            </CardHeader>
            <CardContent>
              {recent.length === 0 ? (
                <p className="text-sm text-zinc-500 text-center py-6">
                  No requests yet. Start a chat to see usage.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-400 text-xs">
                        <th className="text-left py-2 pr-4">Time</th>
                        <th className="text-left py-2 pr-4">Model</th>
                        <th className="text-right py-2 pr-4">Input</th>
                        <th className="text-right py-2 pr-4">Output</th>
                        <th className="text-right py-2 pr-4">Cost</th>
                        <th className="text-left py-2">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.map((r) => (
                        <motion.tr
                          key={r.id}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                        >
                          <td className="py-2 pr-4 text-zinc-400 text-xs">
                            {fmtTime(r.timestamp)}
                          </td>
                          <td className="py-2 pr-4">
                            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300">
                              {r.model.split("/").pop()}
                            </span>
                          </td>
                          <td className="py-2 pr-4 text-right text-zinc-400 text-xs">
                            {fmtTokens(r.input_tokens)}
                          </td>
                          <td className="py-2 pr-4 text-right text-zinc-400 text-xs">
                            {fmtTokens(r.output_tokens)}
                          </td>
                          <td className="py-2 pr-4 text-right text-green-400 text-xs font-mono">
                            {fmtCost(r.cost_usd)}
                          </td>
                          <td className="py-2">
                            <Badge
                              variant="outline"
                              className="text-[10px] py-0 px-1.5"
                            >
                              {r.request_type}
                            </Badge>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </ScrollArea>
    </div>
  );
}
