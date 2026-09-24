export type TargetStatus = "Healthy" | "Warning" | "Down";

export type CheckResult = {
  id: number;
  target_id: string;
  checked_at: string;
  status: TargetStatus;
  http_status_code: number | null;
  response_time_ms: number | null;
  error_message: string | null;
  tls_expires_at: string | null;
  security_score: number | null;
  security_findings: {
    missing?: string[];
    final_url?: string;
    redirect_count?: number;
    tls_days_remaining?: number;
    [key: string]: unknown;
  } | null;
};

export type Target = {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  check_interval_seconds: number;
  created_at: string;
  updated_at: string;
  latest_check: CheckResult | null;
};

export type CreateTargetInput = {
  name: string;
  url: string;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      error instanceof Error
        ? `Could not reach the monitoring API: ${error.message}`
        : "Could not reach the monitoring API.",
      0,
    );
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).filter(Boolean).join(" ") || message;
      }
    } catch {
      // Keep the status-based fallback when the API did not return JSON.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getTargets(signal?: AbortSignal): Promise<Target[]> {
  return request<Target[]>("/targets", { signal });
}

export function createTarget(input: CreateTargetInput): Promise<Target> {
  return request<Target>("/targets", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function runTargetCheck(targetId: string): Promise<CheckResult> {
  return request<CheckResult>(`/targets/${targetId}/checks`, { method: "POST" });
}
