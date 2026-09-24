"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Bell,
  ChevronRight,
  CircleHelp,
  Clock3,
  Globe2,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  Menu,
  Plus,
  Radar,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  ShieldEllipsis,
  X,
  Zap,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
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
  createTarget,
  getTargets,
  runTargetCheck,
  type Target,
} from "@/lib/api";

type DisplayStatus = "Healthy" | "Warning" | "Down" | "Pending" | "Disabled";
type Filter = "All" | "Healthy" | "Warning" | "Down" | "Pending";
type FieldErrors = { name?: string; url?: string };
type AlertItem = {
  severity: "Critical" | "Warning" | "Info";
  title: string;
  detail: string;
  time: string;
};

type ToolDefinition = {
  name: string;
  title?: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
  execute: (input: unknown) => unknown | Promise<unknown>;
};

declare global {
  interface Document {
    modelContext?: {
      registerTool: (
        tool: ToolDefinition,
        options?: { signal?: AbortSignal },
      ) => void | Promise<void>;
    };
  }
}

function displayStatus(target: Target): DisplayStatus {
  if (!target.enabled) return "Disabled";
  return target.latest_check?.status ?? "Pending";
}

function statusStyles(status: DisplayStatus) {
  if (status === "Healthy") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-300";
  if (status === "Warning") return "border-amber-400/20 bg-amber-400/10 text-amber-300";
  if (status === "Down") return "border-rose-400/20 bg-rose-400/10 text-rose-300";
  return "border-slate-400/20 bg-slate-400/10 text-slate-400";
}

function scoreColor(score: number) {
  if (score >= 90) return "text-emerald-300";
  if (score >= 70) return "text-amber-300";
  return "text-rose-300";
}

function relativeTime(timestamp: string | null | undefined) {
  if (!timestamp) return "Never";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - Date.parse(timestamp)) / 1000));
  if (elapsedSeconds < 60) return `${elapsedSeconds} sec ago`;
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.floor(hours / 24)} day${hours < 48 ? "" : "s"} ago`;
}

function tlsDaysRemaining(timestamp: string | null | undefined) {
  if (!timestamp) return null;
  return Math.ceil((Date.parse(timestamp) - Date.now()) / 86_400_000);
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

function validateTargetForm(name: string, rawUrl: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!name.trim()) errors.name = "Enter a display name.";
  else if (name.trim().length > 120) errors.name = "Use 120 characters or fewer.";

  try {
    const parsed = new URL(rawUrl.trim());
    if (!["http:", "https:"].includes(parsed.protocol)) {
      errors.url = "Use an HTTP or HTTPS URL.";
    } else if (parsed.username || parsed.password) {
      errors.url = "URLs with credentials are not allowed.";
    } else if (parsed.port && !["80", "443"].includes(parsed.port)) {
      errors.url = "Only ports 80 and 443 are allowed.";
    } else if (parsed.hash) {
      errors.url = "Remove the URL fragment.";
    }
  } catch {
    errors.url = "Enter a complete URL, such as https://example.com.";
  }
  return errors;
}

export default function Home() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [activeFilter, setActiveFilter] = useState<Filter>("All");
  const [query, setQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [checkingIds, setCheckingIds] = useState<Set<string>>(new Set());
  const targetsRef = useRef(targets);

  useEffect(() => {
    targetsRef.current = targets;
  }, [targets]);

  const loadTargets = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getTargets(signal);
      setTargets(data);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setLoadError(errorMessage(error));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const task = window.setTimeout(() => void loadTargets(controller.signal), 0);
    return () => {
      window.clearTimeout(task);
      controller.abort();
    };
  }, [loadTargets]);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const reportError = (error: unknown) => console.warn("WebMCP tool registration failed", error);
    const registrations = [
      context.registerTool({
        name: "list_monitored_targets",
        title: "List monitored targets",
        description: "Return the targets currently loaded from the monitoring API.",
        inputSchema: { type: "object", properties: {}, additionalProperties: false },
        annotations: { readOnlyHint: true, untrustedContentHint: false },
        execute: () => ({
          count: targetsRef.current.length,
          targets: targetsRef.current.map((target) => ({
            name: target.name,
            url: target.url,
            status: displayStatus(target),
            score: target.latest_check?.security_score ?? null,
          })),
        }),
      }, { signal: lifecycle.signal }),
      context.registerTool({
        name: "add_monitored_target",
        title: "Add monitored target",
        description: "Persist an authorized website through the Sentinel Monitor API.",
        inputSchema: {
          type: "object",
          properties: {
            name: { type: "string", minLength: 1, maxLength: 120 },
            url: { type: "string", minLength: 8 },
          },
          required: ["name", "url"],
          additionalProperties: false,
        },
        annotations: { readOnlyHint: false, untrustedContentHint: false },
        execute: async (input: unknown) => {
          if (!input || typeof input !== "object") throw new Error("A name and URL are required.");
          const candidate = input as { name?: unknown; url?: unknown };
          if (typeof candidate.name !== "string" || typeof candidate.url !== "string") {
            throw new Error("Target name and URL must be strings.");
          }
          const errors = validateTargetForm(candidate.name, candidate.url);
          if (errors.name || errors.url) throw new Error(errors.name ?? errors.url);
          const created = await createTarget({ name: candidate.name.trim(), url: candidate.url.trim() });
          setTargets((current) => [created, ...current]);
          return { id: created.id, status: "saved", name: created.name, url: created.url };
        },
      }, { signal: lifecycle.signal }),
    ];
    registrations.forEach((registration) => Promise.resolve(registration).catch(reportError));
    return () => lifecycle.abort();
  }, []);

  const filteredTargets = useMemo(() => targets.filter((target) => {
    const status = displayStatus(target);
    const matchesFilter = activeFilter === "All" || status === activeFilter;
    return matchesFilter && `${target.name} ${target.url}`.toLowerCase().includes(query.toLowerCase());
  }), [targets, activeFilter, query]);

  const metrics = useMemo(() => {
    const active = targets.filter((target) => target.enabled);
    const checked = active.filter((target) => target.latest_check);
    const healthy = checked.filter((target) => target.latest_check?.status === "Healthy").length;
    const responseTimes = checked.flatMap((target) =>
      target.latest_check?.response_time_ms === null || target.latest_check?.response_time_ms === undefined
        ? []
        : [target.latest_check.response_time_ms]
    );
    const scores = checked.flatMap((target) =>
      target.latest_check?.security_score === null || target.latest_check?.security_score === undefined
        ? []
        : [target.latest_check.security_score]
    );
    return {
      active: active.length,
      checked: checked.length,
      healthy,
      warning: checked.filter((target) => target.latest_check?.status === "Warning").length,
      down: checked.filter((target) => target.latest_check?.status === "Down").length,
      pending: active.length - checked.length,
      availability: checked.length ? `${((healthy / checked.length) * 100).toFixed(1)}%` : "—",
      averageResponse: responseTimes.length
        ? `${Math.round(responseTimes.reduce((sum, value) => sum + value, 0) / responseTimes.length)} ms`
        : "—",
      securityScore: scores.length
        ? Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length)
        : null,
    };
  }, [targets]);

  const alerts = useMemo<AlertItem[]>(() => {
    const generated: AlertItem[] = [];
    for (const target of targets) {
      const check = target.latest_check;
      if (!target.enabled || !check) continue;
      if (check.status === "Down") {
        generated.push({
          severity: "Critical",
          title: `${target.name} is unavailable`,
          detail: check.error_message ?? `Returned HTTP ${check.http_status_code ?? "error"}`,
          time: relativeTime(check.checked_at),
        });
      } else if (check.status === "Warning") {
        generated.push({
          severity: "Warning",
          title: `${target.name} needs attention`,
          detail: check.error_message ?? `Returned HTTP ${check.http_status_code ?? "warning"}`,
          time: relativeTime(check.checked_at),
        });
      }

      const tlsDays = tlsDaysRemaining(check.tls_expires_at);
      if (tlsDays !== null && tlsDays < 30) {
        generated.push({
          severity: "Warning",
          title: `${target.name} certificate expires soon`,
          detail: `${Math.max(0, tlsDays)} days remaining`,
          time: relativeTime(check.checked_at),
        });
      }

      const missing = check.security_findings?.missing;
      if (Array.isArray(missing) && missing.length > 0) {
        generated.push({
          severity: "Info",
          title: `${target.name} can improve security`,
          detail: `${missing.length} recommended header${missing.length === 1 ? " is" : "s are"} missing`,
          time: relativeTime(check.checked_at),
        });
      }
    }
    return generated.slice(0, 5);
  }, [targets]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateTargetForm(name, url);
    setFieldErrors(errors);
    if (errors.name || errors.url) return;

    setSubmitting(true);
    setFormError(null);
    try {
      const created = await createTarget({ name: name.trim(), url: url.trim() });
      setTargets((current) => [created, ...current]);
      setName("");
      setUrl("");
      setFieldErrors({});
      setDialogOpen(false);
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCheck = async (targetId: string) => {
    setCheckingIds((current) => new Set(current).add(targetId));
    setActionError(null);
    try {
      const latestCheck = await runTargetCheck(targetId);
      setTargets((current) => current.map((target) =>
        target.id === targetId ? { ...target, latest_check: latestCheck } : target
      ));
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setCheckingIds((current) => {
        const next = new Set(current);
        next.delete(targetId);
        return next;
      });
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_72%_-12%,rgba(37,99,235,0.16),transparent_33%)]" />
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-white/[0.07] bg-[#080d18] lg:flex lg:flex-col">
        <Brand />
        <nav className="flex-1 px-3 py-6" aria-label="Main navigation">
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Workspace</p>
          <NavItem icon={LayoutDashboard} label="Overview" active />
          <NavItem icon={Globe2} label="Monitors" count={targets.length} />
          <NavItem icon={AlertTriangle} label="Alerts" count={alerts.length} />
          <NavItem icon={Radar} label="Activity" />
          <p className="mt-8 px-3 pb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Configuration</p>
          <NavItem icon={ShieldEllipsis} label="Security rules" />
          <NavItem icon={Bell} label="Notifications" />
          <NavItem icon={Settings} label="Settings" />
        </nav>
        <div className="m-4 rounded-xl border border-blue-400/15 bg-blue-400/[0.06] p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-blue-200"><ShieldCheck className="size-4" /> API connected</div>
          <p className="text-xs leading-5 text-slate-500">Checks use persisted FastAPI results and strict outbound safety controls.</p>
        </div>
      </aside>

      <main className="relative lg:pl-64">
        <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-white/[0.07] bg-background/85 px-4 backdrop-blur-xl sm:px-7 lg:px-9">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="text-slate-400 lg:hidden" onClick={() => setMobileNavOpen((open) => !open)} aria-label="Toggle navigation">
              {mobileNavOpen ? <X /> : <Menu />}
            </Button>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-white sm:text-xl">Security overview</h1>
              <p className="hidden text-sm text-slate-500 sm:block">Live data from the Sentinel Monitor API</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-sm text-slate-400 md:flex">
              <span className={`size-2 rounded-full ${loadError ? "bg-rose-400" : "bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]"}`} />
              {loadError ? "API unavailable" : "API connected"}
            </div>
            <Button variant="ghost" size="icon" className="relative text-slate-400 hover:text-white" aria-label="Notifications">
              <Bell />{alerts.length > 0 && <span className="absolute right-2 top-2 size-1.5 rounded-full bg-rose-400" />}
            </Button>
            <AddTargetDialog
              open={dialogOpen}
              setOpen={(open) => {
                setDialogOpen(open);
                if (!open) {
                  setFieldErrors({});
                  setFormError(null);
                }
              }}
              name={name}
              setName={(value) => { setName(value); setFieldErrors((current) => ({ ...current, name: undefined })); setFormError(null); }}
              url={url}
              setUrl={(value) => { setUrl(value); setFieldErrors((current) => ({ ...current, url: undefined })); setFormError(null); }}
              fieldErrors={fieldErrors}
              formError={formError}
              submitting={submitting}
              onSubmit={handleSubmit}
            />
          </div>
        </header>

        {mobileNavOpen && (
          <nav className="border-b border-white/[0.07] bg-[#080d18] p-3 lg:hidden" aria-label="Mobile navigation">
            <NavItem icon={LayoutDashboard} label="Overview" active />
            <NavItem icon={Globe2} label="Monitors" count={targets.length} />
            <NavItem icon={AlertTriangle} label="Alerts" count={alerts.length} />
          </nav>
        )}

        <div className="mx-auto max-w-[1500px] space-y-6 p-4 sm:p-7 lg:p-9">
          {loadError && (
            <Alert variant="destructive" className="border-rose-400/20 bg-rose-400/[0.06]">
              <AlertCircle />
              <AlertTitle>Could not load monitoring data</AlertTitle>
              <AlertDescription className="sm:flex sm:flex-row sm:items-center sm:justify-between">
                <span>{loadError}</span>
                <Button size="sm" variant="outline" onClick={() => void loadTargets()} disabled={loading}>
                  <RefreshCw className={loading ? "animate-spin" : ""} /> Retry
                </Button>
              </AlertDescription>
            </Alert>
          )}
          {actionError && (
            <Alert variant="destructive" className="border-rose-400/20 bg-rose-400/[0.06]">
              <AlertCircle />
              <AlertTitle>Action failed</AlertTitle>
              <AlertDescription className="sm:flex sm:flex-row sm:items-center sm:justify-between">
                <span>{actionError}</span>
                <Button size="sm" variant="ghost" onClick={() => setActionError(null)}>Dismiss</Button>
              </AlertDescription>
            </Alert>
          )}

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Monitoring summary">
            <MetricCard icon={Globe2} label="Active monitors" value={loading ? "—" : String(metrics.active)} helper={`${metrics.checked} with check results`} tone="blue" />
            <MetricCard icon={Activity} label="Current availability" value={metrics.availability} helper="Based on latest checks" tone="emerald" />
            <MetricCard icon={Zap} label="Avg. response" value={metrics.averageResponse} helper="Across latest responses" tone="violet" />
            <MetricCard icon={ShieldCheck} label="Security score" value={metrics.securityScore === null ? "—" : `${metrics.securityScore}/100`} helper="Average latest score" tone="amber" />
          </section>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(330px,0.75fr)]">
            <div className="panel overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-4 sm:px-6">
                <div><h2 className="font-semibold text-white">Current availability</h2><p className="mt-0.5 text-sm text-slate-500">Latest persisted result for each active monitor</p></div>
                <Button variant="ghost" size="sm" onClick={() => void loadTargets()} disabled={loading} className="text-slate-400">
                  <RefreshCw className={loading ? "animate-spin" : ""} /> Refresh
                </Button>
              </div>
              <div className="p-5 sm:p-6">
                <div className="mb-6 flex items-end gap-3">
                  <strong className="text-3xl font-semibold tracking-tight text-white">{metrics.availability}</strong>
                  <span className="mb-1 text-sm text-slate-500">{metrics.checked ? `${metrics.healthy} of ${metrics.checked} healthy` : "No checks yet"}</span>
                </div>
                <div className="mb-6 flex h-2 overflow-hidden rounded-full bg-white/[0.06]" aria-label="Latest monitor status distribution">
                  {metrics.active > 0 && <>
                    <span className="bg-emerald-400" style={{ width: `${(metrics.healthy / metrics.active) * 100}%` }} />
                    <span className="bg-amber-400" style={{ width: `${(metrics.warning / metrics.active) * 100}%` }} />
                    <span className="bg-rose-400" style={{ width: `${(metrics.down / metrics.active) * 100}%` }} />
                    <span className="bg-slate-600" style={{ width: `${(metrics.pending / metrics.active) * 100}%` }} />
                  </>}
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <StatusCount label="Healthy" value={metrics.healthy} tone="text-emerald-300" />
                  <StatusCount label="Warning" value={metrics.warning} tone="text-amber-300" />
                  <StatusCount label="Down" value={metrics.down} tone="text-rose-300" />
                  <StatusCount label="Pending" value={metrics.pending} tone="text-slate-400" />
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
                <div><h2 className="font-semibold text-white">Latest alerts</h2><p className="mt-0.5 text-sm text-slate-500">Derived from real check results</p></div>
                <Badge variant="outline" className="border-white/[0.08] text-slate-400">{alerts.length}</Badge>
              </div>
              {alerts.length > 0 ? (
                <div className="divide-y divide-white/[0.06] px-5">
                  {alerts.map((alert, index) => (
                    <div key={`${alert.title}-${index}`} className="flex gap-3 py-4">
                      <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${alert.severity === "Critical" ? "bg-rose-400/10 text-rose-300" : alert.severity === "Warning" ? "bg-amber-400/10 text-amber-300" : "bg-blue-400/10 text-blue-300"}`}>
                        {alert.severity === "Info" ? <CircleHelp className="size-4" /> : <AlertTriangle className="size-4" />}
                      </span>
                      <span className="min-w-0 flex-1"><span className="block text-sm font-medium text-slate-200">{alert.title}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{alert.detail}</span><span className="mt-1.5 block text-xs text-slate-600">{alert.time}</span></span>
                      <ChevronRight className="mt-1 size-4 text-slate-700" />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
                  <ShieldCheck className="mb-3 size-7 text-emerald-400/70" />
                  <p className="text-sm font-medium text-slate-300">No current alerts</p>
                  <p className="mt-1 max-w-56 text-sm text-slate-600">Alerts appear after checks report downtime, warnings, or missing protections.</p>
                </div>
              )}
            </div>
          </section>

          <section className="panel overflow-hidden">
            <div className="flex flex-col gap-4 border-b border-white/[0.07] px-5 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
              <div><h2 className="font-semibold text-white">Monitored targets</h2><p className="mt-0.5 text-sm text-slate-500">Persisted targets and their latest security check</p></div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex gap-1 overflow-x-auto rounded-lg border border-white/[0.07] bg-white/[0.02] p-1">
                  {(["All", "Healthy", "Warning", "Down", "Pending"] as Filter[]).map((filter) => (
                    <button key={filter} onClick={() => setActiveFilter(filter)} className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${activeFilter === filter ? "bg-white/[0.09] text-white" : "text-slate-500 hover:text-slate-300"}`}>{filter}</button>
                  ))}
                </div>
                <label className="relative block">
                  <span className="sr-only">Search targets</span>
                  <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-600" />
                  <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search targets" className="h-9 w-full border-white/[0.08] bg-white/[0.025] pl-9 text-sm sm:w-52" />
                </label>
              </div>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow className="border-white/[0.06] hover:bg-transparent"><TableHead className="h-11 pl-6 text-xs uppercase tracking-wider text-slate-600">Target</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Status</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">HTTP</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Response</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">TLS</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Score</TableHead><TableHead className="pr-6 text-right text-xs uppercase tracking-wider text-slate-600">Latest check</TableHead></TableRow></TableHeader>
                <TableBody>
                  {loading && targets.length === 0 ? <LoadingRows /> : filteredTargets.map((target) => {
                    const status = displayStatus(target);
                    const check = target.latest_check;
                    const tlsDays = tlsDaysRemaining(check?.tls_expires_at);
                    const checking = checkingIds.has(target.id);
                    return (
                      <TableRow key={target.id} className="border-white/[0.06] hover:bg-white/[0.025]">
                        <TableCell className="py-4 pl-6"><div className="flex items-center gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.035] text-slate-400"><Globe2 className="size-4" /></span><span><span className="block text-sm font-medium text-slate-200">{target.name}</span><span className="mt-0.5 block max-w-52 truncate text-xs text-slate-600">{target.url}</span></span></div></TableCell>
                        <TableCell><Badge variant="outline" className={`gap-1.5 font-medium ${statusStyles(status)}`}><span className="size-1.5 rounded-full bg-current" />{status}</Badge></TableCell>
                        <TableCell className="text-sm text-slate-300">{check?.http_status_code ?? "—"}</TableCell>
                        <TableCell className="text-sm text-slate-300">{check?.response_time_ms === null || check?.response_time_ms === undefined ? "Pending" : `${check.response_time_ms} ms`}</TableCell>
                        <TableCell><span className={`inline-flex items-center gap-1.5 text-sm ${tlsDays === null ? "text-slate-500" : tlsDays > 30 ? "text-slate-300" : "text-amber-300"}`}><LockKeyhole className="size-3.5" />{tlsDays === null ? "—" : `${Math.max(0, tlsDays)} days`}</span></TableCell>
                        <TableCell>{check?.security_score === null || check?.security_score === undefined ? <span className="text-slate-600">—</span> : <div className="flex w-28 items-center gap-2"><Progress value={check.security_score} className="h-1.5 bg-white/[0.07]" /><span className={`w-6 text-xs font-semibold ${scoreColor(check.security_score)}`}>{check.security_score}</span></div>}</TableCell>
                        <TableCell className="pr-6 text-right"><span className="block text-xs text-slate-500">{relativeTime(check?.checked_at)}</span><Button size="xs" variant="ghost" disabled={checking || !target.enabled} onClick={() => void handleCheck(target.id)} className="mt-1 text-blue-400 hover:text-blue-300">{checking ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} {checking ? "Checking" : "Check now"}</Button></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {!loading && targets.length === 0 && (
                <div className="flex flex-col items-center px-6 py-14 text-center"><Globe2 className="mb-3 size-7 text-slate-700" /><p className="text-sm font-medium text-slate-300">No monitored targets yet</p><p className="mt-1 max-w-sm text-sm text-slate-600">Add an authorized website to start collecting availability and security results.</p><Button size="sm" className="mt-4 bg-blue-500 text-white hover:bg-blue-400" onClick={() => setDialogOpen(true)}><Plus /> Add your first target</Button></div>
              )}
              {!loading && targets.length > 0 && filteredTargets.length === 0 && (
                <div className="flex flex-col items-center px-6 py-12 text-center"><Search className="mb-3 size-6 text-slate-700" /><p className="text-sm font-medium text-slate-300">No targets found</p><p className="mt-1 text-sm text-slate-600">Try another search or status filter.</p></div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function Brand() {
  return <div className="flex h-20 items-center gap-3 border-b border-white/[0.07] px-6"><span className="relative flex size-9 items-center justify-center rounded-xl bg-blue-500 text-white shadow-[0_0_28px_rgba(59,130,246,0.24)]"><ShieldCheck className="size-5" /></span><span><span className="block text-sm font-semibold tracking-wide text-white">SENTINEL</span><span className="block text-[11px] font-medium uppercase tracking-[0.22em] text-blue-400">Monitor</span></span></div>;
}

function NavItem({ icon: Icon, label, active = false, count }: { icon: typeof Server; label: string; active?: boolean; count?: number }) {
  return <button className={`mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${active ? "bg-blue-500/10 text-blue-300" : "text-slate-500 hover:bg-white/[0.035] hover:text-slate-300"}`}><Icon className="size-[18px]" /><span>{label}</span>{count !== undefined && <span className={`ml-auto min-w-5 rounded px-1.5 py-0.5 text-center text-[11px] ${active ? "bg-blue-400/15" : "bg-white/[0.05]"}`}>{count}</span>}</button>;
}

function MetricCard({ icon: Icon, label, value, helper, tone }: { icon: typeof Activity; label: string; value: string; helper: string; tone: "blue" | "emerald" | "violet" | "amber" }) {
  const tones = { blue: "bg-blue-400/10 text-blue-300", emerald: "bg-emerald-400/10 text-emerald-300", violet: "bg-violet-400/10 text-violet-300", amber: "bg-amber-400/10 text-amber-300" };
  return <div className="panel p-5"><div className="mb-5 flex items-start justify-between"><span className={`flex size-10 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="size-[18px]" /></span><span className="flex items-center gap-1 text-xs text-slate-600"><Clock3 className="size-3" /> live</span></div><p className="text-sm text-slate-500">{label}</p><p className="mt-1 text-2xl font-semibold tracking-tight text-white">{value}</p><p className="mt-2 text-xs text-slate-600">{helper}</p></div>;
}

function StatusCount({ label, value, tone }: { label: string; value: number; tone: string }) {
  return <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className={`text-xl font-semibold ${tone}`}>{value}</p><p className="mt-1 text-xs text-slate-600">{label}</p></div>;
}

function LoadingRows() {
  return <>{Array.from({ length: 4 }, (_, index) => <TableRow key={index} className="border-white/[0.06]"><TableCell className="py-5 pl-6"><div className="flex items-center gap-3"><Skeleton className="size-9 bg-white/[0.06]" /><div className="space-y-2"><Skeleton className="h-3 w-28 bg-white/[0.06]" /><Skeleton className="h-2.5 w-40 bg-white/[0.04]" /></div></div></TableCell>{Array.from({ length: 5 }, (_, cell) => <TableCell key={cell}><Skeleton className="h-4 w-16 bg-white/[0.05]" /></TableCell>)}<TableCell className="pr-6"><Skeleton className="ml-auto h-6 w-20 bg-white/[0.05]" /></TableCell></TableRow>)}</>;
}

function AddTargetDialog({ open, setOpen, name, setName, url, setUrl, fieldErrors, formError, submitting, onSubmit }: { open: boolean; setOpen: (open: boolean) => void; name: string; setName: (value: string) => void; url: string; setUrl: (value: string) => void; fieldErrors: FieldErrors; formError: string | null; submitting: boolean; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="h-9 bg-blue-500 px-3 text-white shadow-[0_8px_24px_rgba(37,99,235,0.2)] hover:bg-blue-400 sm:px-4"><Plus className="size-4" /><span className="hidden sm:inline">Add target</span></Button></DialogTrigger>
      <DialogContent className="border-white/[0.09] bg-[#0d1422] text-white shadow-2xl sm:max-w-md">
        <form onSubmit={onSubmit} noValidate>
          <DialogHeader><DialogTitle>Add a monitored target</DialogTitle><DialogDescription className="text-slate-500">Only monitor websites and servers you own or are authorized to test.</DialogDescription></DialogHeader>
          <div className="space-y-4 py-6">
            {formError && <Alert variant="destructive" className="border-rose-500/20 bg-rose-500/[0.06]"><AlertCircle /><AlertTitle>Could not add target</AlertTitle><AlertDescription>{formError}</AlertDescription></Alert>}
            <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Display name</span><Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Portfolio website" className="border-white/[0.09] bg-white/[0.035]" autoFocus aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? "name-error" : undefined} disabled={submitting} />{fieldErrors.name && <span id="name-error" className="mt-1.5 block text-xs text-rose-300">{fieldErrors.name}</span>}</label>
            <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Website URL</span><Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" className="border-white/[0.09] bg-white/[0.035]" aria-invalid={Boolean(fieldErrors.url)} aria-describedby={fieldErrors.url ? "url-error" : undefined} disabled={submitting} />{fieldErrors.url && <span id="url-error" className="mt-1.5 block text-xs text-rose-300">{fieldErrors.url}</span>}</label>
          </div>
          <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)} className="text-slate-400" disabled={submitting}>Cancel</Button><Button type="submit" className="bg-blue-500 text-white hover:bg-blue-400" disabled={submitting}>{submitting && <LoaderCircle className="animate-spin" />}{submitting ? "Saving" : "Add target"}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
