"use client";

import { RedirectToSignIn, UserButton, useAuth } from "@clerk/react";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Globe2,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Timer,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  getTargetHistory,
  runTargetCheck,
  type CheckHistoryPage,
  type TargetStatus,
} from "@/lib/api";

const PAGE_SIZE = 50;
const RANGE_OPTIONS = [
  { label: "24 hours", days: 1 },
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
] as const;

const latencyConfig = {
  responseTime: { label: "Response time", color: "var(--chart-1)" },
} satisfies ChartConfig;

const statusConfig = {
  statusValue: { label: "Status", color: "var(--chart-2)" },
} satisfies ChartConfig;

const STATUS_VALUE: Record<TargetStatus, number> = {
  Down: 0,
  Warning: 1,
  Healthy: 2,
};

function errorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

function statusStyles(status: TargetStatus) {
  if (status === "Healthy") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-300";
  if (status === "Warning") return "border-amber-400/20 bg-amber-400/10 text-amber-300";
  return "border-rose-400/20 bg-rose-400/10 text-rose-300";
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatChartTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(value: number) {
  if (value === 2) return "Healthy";
  if (value === 1) return "Warning";
  return "Down";
}

export default function TargetDetailsPage() {
  const { targetId } = useParams<{ targetId: string }>();
  const { getToken, isLoaded: authLoaded, isSignedIn } = useAuth();
  const [rangeDays, setRangeDays] = useState(7);
  const [rangeEnd, setRangeEnd] = useState(() => new Date().toISOString());
  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState<CheckHistoryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    if (!authLoaded || !isSignedIn) return;
    setLoading(true);
    setError(null);
    try {
      const accessToken = await getToken();
      if (!accessToken) throw new ApiError("Your session expired. Please sign in again.", 401);
      const from = new Date(
        Date.parse(rangeEnd) - rangeDays * 86_400_000,
      ).toISOString();
      const data = await getTargetHistory(
        targetId,
        { limit: PAGE_SIZE, offset, from, to: rangeEnd },
        accessToken,
        signal,
      );
      setHistory(data);
    } catch (loadError) {
      if (loadError instanceof DOMException && loadError.name === "AbortError") return;
      setError(errorMessage(loadError));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [authLoaded, getToken, isSignedIn, offset, rangeDays, rangeEnd, targetId]);

  useEffect(() => {
    const controller = new AbortController();
    const task = window.setTimeout(() => void loadHistory(controller.signal), 0);
    return () => {
      window.clearTimeout(task);
      controller.abort();
    };
  }, [loadHistory]);

  const chartData = useMemo(() => (
    history?.series.map((check) => ({
      checkedAt: check.checked_at,
      responseTime: check.response_time_ms,
      statusValue: STATUS_VALUE[check.status],
      status: check.status,
    })) ?? []
  ), [history]);

  const handleCheck = async () => {
    setChecking(true);
    setError(null);
    try {
      const accessToken = await getToken();
      if (!accessToken) throw new ApiError("Your session expired. Please sign in again.", 401);
      await runTargetCheck(targetId, accessToken);
      setOffset(0);
      setRangeEnd(new Date().toISOString());
    } catch (checkError) {
      setError(errorMessage(checkError));
    } finally {
      setChecking(false);
    }
  };

  if (!authLoaded) {
    return <div className="flex min-h-screen items-center justify-center bg-background"><LoaderCircle className="size-6 animate-spin text-blue-400" /></div>;
  }
  if (!isSignedIn) return <RedirectToSignIn />;

  const summary = history?.summary;
  const target = history?.target;
  const pageStart = history && history.total > 0 ? history.offset + 1 : 0;
  const pageEnd = history ? Math.min(history.offset + history.items.length, history.total) : 0;

  return (
    <main className="min-h-screen bg-background px-4 py-6 text-foreground sm:px-6 lg:px-10">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <Button asChild variant="outline" size="icon" aria-label="Back to dashboard">
              <Link href="/"><ArrowLeft /></Link>
            </Button>
            <span className="flex size-11 items-center justify-center rounded-xl bg-blue-500 text-white shadow-[0_0_28px_rgba(59,130,246,0.24)]"><ShieldCheck className="size-6" /></span>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-blue-400">Target history</p>
              <h1 className="text-xl font-semibold text-white">{target?.name ?? "Loading target…"}</h1>
              <p className="mt-1 text-sm text-slate-500">{target?.url ?? "Historical availability and response time"}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={() => void handleCheck()} disabled={checking || !target} className="bg-blue-500 text-white hover:bg-blue-400">
              {checking ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} {checking ? "Checking" : "Check now"}
            </Button>
            <UserButton />
          </div>
        </header>

        {error ? <Alert variant="destructive"><AlertCircle /><AlertTitle>Could not load history</AlertTitle><AlertDescription>{error}</AlertDescription></Alert> : null}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Historical summary">
          <SummaryCard icon={Activity} label="Uptime" value={summary?.uptime_percentage == null ? "—" : `${summary.uptime_percentage.toFixed(2)}%`} helper={`${summary?.available_checks ?? 0} of ${summary?.total_checks ?? 0} available`} />
          <SummaryCard icon={Timer} label="Average response" value={summary?.average_response_time_ms == null ? "—" : `${Math.round(summary.average_response_time_ms)} ms`} helper="Successful and failed responses with latency" />
          <SummaryCard icon={CheckCircle2} label="Checks" value={String(summary?.total_checks ?? 0)} helper={`Selected ${rangeDays}-day range`} />
          <SummaryCard icon={Clock3} label="Response range" value={summary?.minimum_response_time_ms == null ? "—" : `${summary.minimum_response_time_ms}–${summary.maximum_response_time_ms} ms`} helper="Minimum to maximum" />
        </section>

        <section className="panel p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div><h2 className="font-semibold text-white">History window</h2><p className="mt-1 text-sm text-slate-500">Aggregates cover every check in the selected range.</p></div>
            <div className="flex flex-wrap gap-2">
              {RANGE_OPTIONS.map((option) => <Button key={option.days} size="sm" variant={rangeDays === option.days ? "default" : "outline"} onClick={() => { setRangeDays(option.days); setRangeEnd(new Date().toISOString()); setOffset(0); }}>{option.label}</Button>)}
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <HistoryChart title="Response-time history" description={`Showing ${chartData.length} points across ${history?.total ?? 0} checks in this range`}>
            <ChartContainer config={latencyConfig} className="h-[300px] w-full aspect-auto">
              <LineChart data={chartData} accessibilityLayer margin={{ left: 8, right: 16, top: 12 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="checkedAt" tickFormatter={formatChartTime} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis unit=" ms" width={64} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => formatTimestamp(String(value))} />} />
                <Line type="monotone" dataKey="responseTime" stroke="var(--color-responseTime)" strokeWidth={2} dot={false} connectNulls={false} />
              </LineChart>
            </ChartContainer>
          </HistoryChart>
          <HistoryChart title="Status history" description="Healthy and warning count as available; Down counts as downtime">
            <ChartContainer config={statusConfig} className="h-[300px] w-full aspect-auto">
              <LineChart data={chartData} accessibilityLayer margin={{ left: 8, right: 16, top: 12 }}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="checkedAt" tickFormatter={formatChartTime} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis domain={[0, 2]} ticks={[0, 1, 2]} tickFormatter={statusLabel} width={64} tickLine={false} axisLine={false} />
                <ChartTooltip content={<ChartTooltipContent labelFormatter={(value) => formatTimestamp(String(value))} formatter={(value) => <span className="font-medium text-white">{statusLabel(Number(value))}</span>} />} />
                <Line type="stepAfter" dataKey="statusValue" stroke="var(--color-statusValue)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ChartContainer>
          </HistoryChart>
        </section>

        <section className="panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4"><div><h2 className="font-semibold text-white">Check results</h2><p className="mt-1 text-sm text-slate-500">{pageStart}–{pageEnd} of {history?.total ?? 0}</p></div><Globe2 className="size-5 text-slate-500" /></div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">Checked at</TableHead><TableHead>Status</TableHead><TableHead>HTTP</TableHead><TableHead>Response</TableHead><TableHead>Security</TableHead><TableHead className="pr-5">Detail</TableHead></TableRow></TableHeader>
              <TableBody>
                {history?.items.map((check) => <TableRow key={check.id}><TableCell className="pl-5 whitespace-nowrap text-slate-300">{formatTimestamp(check.checked_at)}</TableCell><TableCell><Badge variant="outline" className={statusStyles(check.status)}>{check.status}</Badge></TableCell><TableCell>{check.http_status_code ?? "—"}</TableCell><TableCell>{check.response_time_ms == null ? "—" : `${check.response_time_ms} ms`}</TableCell><TableCell>{check.security_score == null ? "—" : `${check.security_score}/100`}</TableCell><TableCell className="max-w-72 truncate pr-5 text-slate-500">{check.error_message ?? "Completed"}</TableCell></TableRow>)}
              </TableBody>
            </Table>
            {!loading && history?.items.length === 0 ? <div className="px-6 py-12 text-center text-sm text-slate-500">No checks were recorded in this date range.</div> : null}
            {loading ? <div className="flex items-center justify-center gap-2 px-6 py-12 text-sm text-slate-500"><LoaderCircle className="size-4 animate-spin" /> Loading history…</div> : null}
          </div>
          <div className="flex justify-end gap-2 border-t border-white/[0.07] px-5 py-4"><Button variant="outline" size="sm" disabled={loading || offset === 0} onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}>Previous</Button><Button variant="outline" size="sm" disabled={loading || !history || offset + history.items.length >= history.total} onClick={() => setOffset((current) => current + PAGE_SIZE)}>Next</Button></div>
        </section>
      </div>
    </main>
  );
}

function SummaryCard({ icon: Icon, label, value, helper }: { icon: typeof Activity; label: string; value: string; helper: string }) {
  return <Card className="border-white/[0.07] bg-white/[0.025]"><CardContent className="p-5"><div className="flex items-center gap-2 text-sm text-slate-500"><Icon className="size-4 text-blue-400" />{label}</div><p className="mt-3 text-2xl font-semibold text-white">{value}</p><p className="mt-1 text-xs text-slate-600">{helper}</p></CardContent></Card>;
}

function HistoryChart({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <Card className="border-white/[0.07] bg-white/[0.025]"><CardHeader><CardTitle className="text-base text-white">{title}</CardTitle><p className="text-sm text-slate-500">{description}</p></CardHeader><CardContent>{children}</CardContent></Card>;
}
