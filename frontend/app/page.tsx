"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronRight,
  CircleHelp,
  Clock3,
  Globe2,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Plus,
  Radar,
  Search,
  Server,
  Settings,
  ShieldCheck,
  ShieldEllipsis,
  X,
  Zap,
} from "lucide-react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type TargetStatus = "Healthy" | "Warning" | "Down";

type Target = {
  id: number;
  name: string;
  url: string;
  status: TargetStatus;
  uptime: string;
  responseTime: string;
  sslDays: number;
  score: number;
  checked: string;
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

const initialTargets: Target[] = [
  { id: 1, name: "Portfolio website", url: "https://example.com", status: "Healthy", uptime: "99.99%", responseTime: "184 ms", sslDays: 72, score: 96, checked: "28 sec ago" },
  { id: 2, name: "Public API", url: "https://api.example.com", status: "Warning", uptime: "99.82%", responseTime: "648 ms", sslDays: 18, score: 74, checked: "1 min ago" },
  { id: 3, name: "Status page", url: "https://status.example.com", status: "Healthy", uptime: "100%", responseTime: "121 ms", sslDays: 91, score: 98, checked: "2 min ago" },
  { id: 4, name: "Staging server", url: "https://staging.example.com", status: "Down", uptime: "97.41%", responseTime: "Timeout", sslDays: 43, score: 42, checked: "3 min ago" },
];

const alerts = [
  { severity: "Critical", title: "Staging server is unreachable", detail: "Connection timed out after 10 seconds", time: "3 min ago" },
  { severity: "Warning", title: "TLS certificate expires soon", detail: "Public API certificate expires in 18 days", time: "12 min ago" },
  { severity: "Info", title: "Security score improved", detail: "Portfolio website added an HSTS header", time: "1 hr ago" },
];

const chartPoints = "0,79 45,70 90,72 135,54 180,60 225,44 270,49 315,35 360,41 405,26 450,33 495,20 540,24 585,14 630,17";

function statusStyles(status: TargetStatus) {
  if (status === "Healthy") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-300";
  if (status === "Warning") return "border-amber-400/20 bg-amber-400/10 text-amber-300";
  return "border-rose-400/20 bg-rose-400/10 text-rose-300";
}

function scoreColor(score: number) {
  if (score >= 90) return "text-emerald-300";
  if (score >= 70) return "text-amber-300";
  return "text-rose-300";
}

export default function Home() {
  const [targets, setTargets] = useState(initialTargets);
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const targetsRef = useRef(targets);

  useEffect(() => {
    targetsRef.current = targets;
  }, [targets]);

  const addTarget = (targetName: string, targetUrl: string) => {
    const normalizedUrl = /^https?:\/\//i.test(targetUrl) ? targetUrl : `https://${targetUrl}`;
    const nextTarget: Target = {
      id: Date.now(), name: targetName.trim(), url: normalizedUrl.trim(), status: "Healthy",
      uptime: "Pending", responseTime: "Pending", sslDays: 0, score: 0, checked: "Queued",
    };
    setTargets((current) => [nextTarget, ...current]);
    return nextTarget;
  };

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const reportError = (error: unknown) => console.warn("WebMCP tool registration failed", error);
    const registrations = [
      context.registerTool({
        name: "list_monitored_targets",
        title: "List monitored targets",
        description: "Return the targets currently visible in the monitoring dashboard.",
        inputSchema: { type: "object", properties: {}, additionalProperties: false },
        annotations: { readOnlyHint: true, untrustedContentHint: false },
        execute: () => ({
          count: targetsRef.current.length,
          targets: targetsRef.current.map(({ name: targetName, url: targetUrl, status, score }) => ({ name: targetName, url: targetUrl, status, score })),
        }),
      }, { signal: lifecycle.signal }),
      context.registerTool({
        name: "add_monitored_target",
        title: "Add monitored target",
        description: "Add an authorized website to the visible monitoring queue.",
        inputSchema: {
          type: "object",
          properties: { name: { type: "string", minLength: 1 }, url: { type: "string", minLength: 3 } },
          required: ["name", "url"],
          additionalProperties: false,
        },
        annotations: { readOnlyHint: false, untrustedContentHint: false },
        execute: (input: unknown) => {
          if (!input || typeof input !== "object") throw new Error("A name and URL are required.");
          const candidate = input as { name?: unknown; url?: unknown };
          if (typeof candidate.name !== "string" || !candidate.name.trim()) throw new Error("Target name must be a non-empty string.");
          if (typeof candidate.url !== "string" || candidate.url.trim().length < 3) throw new Error("Target URL must be a valid non-empty string.");
          const created = addTarget(candidate.name, candidate.url);
          return { id: created.id, status: "queued", name: created.name, url: created.url };
        },
      }, { signal: lifecycle.signal }),
    ];
    registrations.forEach((registration) => Promise.resolve(registration).catch(reportError));
    return () => lifecycle.abort();
  }, []);

  const filteredTargets = useMemo(() => targets.filter((target) => {
    const matchesFilter = activeFilter === "All" || target.status === activeFilter;
    return matchesFilter && `${target.name} ${target.url}`.toLowerCase().includes(query.toLowerCase());
  }), [targets, activeFilter, query]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || !url.trim()) return;
    addTarget(name, url);
    setName(""); setUrl(""); setDialogOpen(false);
  };

  const healthyCount = targets.filter((target) => target.status === "Healthy").length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_72%_-12%,rgba(37,99,235,0.16),transparent_33%)]" />
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-white/[0.07] bg-[#080d18] lg:flex lg:flex-col">
        <Brand />
        <nav className="flex-1 px-3 py-6" aria-label="Main navigation">
          <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Workspace</p>
          <NavItem icon={LayoutDashboard} label="Overview" active />
          <NavItem icon={Globe2} label="Monitors" count={targets.length} />
          <NavItem icon={AlertTriangle} label="Alerts" count={2} />
          <NavItem icon={Radar} label="Activity" />
          <p className="mt-8 px-3 pb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">Configuration</p>
          <NavItem icon={ShieldEllipsis} label="Security rules" />
          <NavItem icon={Bell} label="Notifications" />
          <NavItem icon={Settings} label="Settings" />
        </nav>
        <div className="m-4 rounded-xl border border-blue-400/15 bg-blue-400/[0.06] p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-blue-200"><ShieldCheck className="size-4" /> Monitoring active</div>
          <p className="text-xs leading-5 text-slate-500">All checks run from the primary region every 5 minutes.</p>
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
              <p className="hidden text-sm text-slate-500 sm:block">Tuesday, 23 September · Bengaluru region</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-sm text-slate-400 md:flex">
              <span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]" /> Live monitoring
            </div>
            <Button variant="ghost" size="icon" className="relative text-slate-400 hover:text-white" aria-label="Notifications">
              <Bell /><span className="absolute right-2 top-2 size-1.5 rounded-full bg-rose-400" />
            </Button>
            <AddTargetDialog open={dialogOpen} setOpen={setDialogOpen} name={name} setName={setName} url={url} setUrl={setUrl} onSubmit={handleSubmit} />
          </div>
        </header>

        {mobileNavOpen && (
          <nav className="border-b border-white/[0.07] bg-[#080d18] p-3 lg:hidden" aria-label="Mobile navigation">
            <NavItem icon={LayoutDashboard} label="Overview" active />
            <NavItem icon={Globe2} label="Monitors" count={targets.length} />
            <NavItem icon={AlertTriangle} label="Alerts" count={2} />
          </nav>
        )}

        <div className="mx-auto max-w-[1500px] space-y-6 p-4 sm:p-7 lg:p-9">
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Monitoring summary">
            <MetricCard icon={Globe2} label="Active monitors" value={String(targets.length)} helper={`${healthyCount} responding normally`} tone="blue" />
            <MetricCard icon={Activity} label="Overall uptime" value="99.81%" helper="Last 30 days" tone="emerald" />
            <MetricCard icon={Zap} label="Avg. response" value="238 ms" helper="26 ms faster this week" tone="violet" />
            <MetricCard icon={ShieldCheck} label="Security score" value="84/100" helper="Good · 2 actions needed" tone="amber" />
          </section>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(330px,0.75fr)]">
            <div className="panel overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] px-5 py-4 sm:px-6">
                <div><h2 className="font-semibold text-white">Availability</h2><p className="mt-0.5 text-sm text-slate-500">Successful checks across all monitors</p></div>
                <div className="flex rounded-lg border border-white/[0.07] bg-white/[0.02] p-1 text-xs font-medium">
                  <button className="rounded-md bg-white/[0.08] px-3 py-1.5 text-white">24h</button>
                  <button className="px-3 py-1.5 text-slate-500 transition hover:text-slate-300">7d</button>
                  <button className="px-3 py-1.5 text-slate-500 transition hover:text-slate-300">30d</button>
                </div>
              </div>
              <div className="p-5 sm:p-6">
                <div className="mb-5 flex items-end gap-3"><strong className="text-3xl font-semibold tracking-tight text-white">99.97%</strong><span className="mb-1 rounded bg-emerald-400/10 px-2 py-0.5 text-xs font-medium text-emerald-300">+0.12%</span></div>
                <div className="relative h-40 w-full" aria-label="Availability trend chart">
                  <div className="absolute inset-0 flex flex-col justify-between">{[100, 75, 50, 25, 0].map((line) => <div key={line} className="border-t border-dashed border-white/[0.06]" />)}</div>
                  <svg viewBox="0 0 630 100" className="absolute inset-0 h-full w-full overflow-visible" preserveAspectRatio="none" role="img" aria-label="Availability increased during the last 24 hours">
                    <defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity="0.32" /><stop offset="100%" stopColor="#3b82f6" stopOpacity="0" /></linearGradient></defs>
                    <polygon points={`0,100 ${chartPoints} 630,100`} fill="url(#chartFill)" />
                    <polyline points={chartPoints} fill="none" stroke="#60a5fa" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
                    <circle cx="630" cy="17" r="4" fill="#93c5fd" stroke="#0b1120" strokeWidth="3" />
                  </svg>
                </div>
                <div className="mt-3 flex justify-between text-xs text-slate-600"><span>12 AM</span><span>6 AM</span><span>12 PM</span><span>6 PM</span><span>Now</span></div>
              </div>
            </div>

            <div className="panel">
              <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
                <div><h2 className="font-semibold text-white">Recent alerts</h2><p className="mt-0.5 text-sm text-slate-500">Needs your attention</p></div>
                <button className="text-sm font-medium text-blue-400 transition hover:text-blue-300">View all</button>
              </div>
              <div className="divide-y divide-white/[0.06] px-5">
                {alerts.map((alert) => (
                  <button key={alert.title} className="group flex w-full gap-3 py-4 text-left">
                    <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${alert.severity === "Critical" ? "bg-rose-400/10 text-rose-300" : alert.severity === "Warning" ? "bg-amber-400/10 text-amber-300" : "bg-blue-400/10 text-blue-300"}`}>
                      {alert.severity === "Info" ? <CircleHelp className="size-4" /> : <AlertTriangle className="size-4" />}
                    </span>
                    <span className="min-w-0 flex-1"><span className="block text-sm font-medium text-slate-200 group-hover:text-white">{alert.title}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{alert.detail}</span><span className="mt-1.5 block text-xs text-slate-600">{alert.time}</span></span>
                    <ChevronRight className="mt-1 size-4 text-slate-700 transition group-hover:translate-x-0.5 group-hover:text-slate-400" />
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="panel overflow-hidden">
            <div className="flex flex-col gap-4 border-b border-white/[0.07] px-5 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
              <div><h2 className="font-semibold text-white">Monitored targets</h2><p className="mt-0.5 text-sm text-slate-500">Health and security posture of authorized websites</p></div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex gap-1 rounded-lg border border-white/[0.07] bg-white/[0.02] p-1">
                  {["All", "Healthy", "Warning", "Down"].map((filter) => (
                    <button key={filter} onClick={() => setActiveFilter(filter)} className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${activeFilter === filter ? "bg-white/[0.09] text-white" : "text-slate-500 hover:text-slate-300"}`}>{filter}</button>
                  ))}
                </div>
                <label className="relative block">
                  <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-600" />
                  <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search targets" className="h-9 w-full border-white/[0.08] bg-white/[0.025] pl-9 text-sm sm:w-52" />
                </label>
              </div>
            </div>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow className="border-white/[0.06] hover:bg-transparent"><TableHead className="h-11 pl-6 text-xs uppercase tracking-wider text-slate-600">Target</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Status</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Uptime</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Response</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">SSL</TableHead><TableHead className="text-xs uppercase tracking-wider text-slate-600">Score</TableHead><TableHead className="pr-6 text-right text-xs uppercase tracking-wider text-slate-600">Last checked</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredTargets.map((target) => (
                    <TableRow key={target.id} className="border-white/[0.06] hover:bg-white/[0.025]">
                      <TableCell className="py-4 pl-6"><div className="flex items-center gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.07] bg-white/[0.035] text-slate-400"><Globe2 className="size-4" /></span><span><span className="block text-sm font-medium text-slate-200">{target.name}</span><span className="mt-0.5 block max-w-52 truncate text-xs text-slate-600">{target.url}</span></span></div></TableCell>
                      <TableCell><Badge variant="outline" className={`gap-1.5 font-medium ${statusStyles(target.status)}`}><span className="size-1.5 rounded-full bg-current" />{target.status}</Badge></TableCell>
                      <TableCell className="text-sm text-slate-300">{target.uptime}</TableCell>
                      <TableCell className="text-sm text-slate-300">{target.responseTime}</TableCell>
                      <TableCell><span className={`inline-flex items-center gap-1.5 text-sm ${target.sslDays > 30 ? "text-slate-300" : target.sslDays > 0 ? "text-amber-300" : "text-slate-500"}`}><LockKeyhole className="size-3.5" />{target.sslDays > 0 ? `${target.sslDays} days` : "Pending"}</span></TableCell>
                      <TableCell><div className="flex w-28 items-center gap-2"><Progress value={target.score} className="h-1.5 bg-white/[0.07]" /><span className={`w-6 text-xs font-semibold ${scoreColor(target.score)}`}>{target.score || "—"}</span></div></TableCell>
                      <TableCell className="pr-6 text-right text-xs text-slate-500">{target.checked}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {filteredTargets.length === 0 && <div className="flex flex-col items-center px-6 py-12 text-center"><Search className="mb-3 size-6 text-slate-700" /><p className="text-sm font-medium text-slate-300">No targets found</p><p className="mt-1 text-sm text-slate-600">Try another search or status filter.</p></div>}
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

function AddTargetDialog({ open, setOpen, name, setName, url, setUrl, onSubmit }: { open: boolean; setOpen: (open: boolean) => void; name: string; setName: (value: string) => void; url: string; setUrl: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button className="h-9 bg-blue-500 px-3 text-white shadow-[0_8px_24px_rgba(37,99,235,0.2)] hover:bg-blue-400 sm:px-4"><Plus className="size-4" /><span className="hidden sm:inline">Add target</span></Button></DialogTrigger>
      <DialogContent className="border-white/[0.09] bg-[#0d1422] text-white shadow-2xl sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader><DialogTitle>Add a monitored target</DialogTitle><DialogDescription className="text-slate-500">Only monitor websites and servers you own or are authorized to test.</DialogDescription></DialogHeader>
          <div className="space-y-4 py-6">
            <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Display name</span><Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Portfolio website" className="border-white/[0.09] bg-white/[0.035]" autoFocus required /></label>
            <label className="block"><span className="mb-2 block text-sm font-medium text-slate-300">Website URL</span><Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" className="border-white/[0.09] bg-white/[0.035]" required /></label>
          </div>
          <DialogFooter><Button type="button" variant="ghost" onClick={() => setOpen(false)} className="text-slate-400">Cancel</Button><Button type="submit" className="bg-blue-500 text-white hover:bg-blue-400">Start monitoring</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
