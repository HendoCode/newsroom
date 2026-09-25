"use client";

import * as React from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

interface AgentsHealthResult {
  reachable: boolean;
  agents?: { status: string; service: string; version: string };
  error?: string;
}

/**
 * Client component that calls the same-origin BFF route (/api/agents/health), which in turn
 * proxies the Python agents service over REST. Renders live web/ ↔ agents/ connectivity —
 * the browser never learns the agents URL. Demonstrates the wiring required by the acceptance
 * criteria.
 */
export function AgentsStatus() {
  const [result, setResult] = React.useState<AgentsHealthResult | null>(null);
  const [loading, setLoading] = React.useState(true);

  const check = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/agents/health", { cache: "no-store" });
      setResult((await res.json()) as AgentsHealthResult);
    } catch (error) {
      setResult({
        reachable: false,
        error: error instanceof Error ? error.message : "request failed",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void check();
  }, [check]);

  const reachable = result?.reachable ?? false;

  return (
    <div className="flex items-center gap-3 rounded-md border bg-muted/40 px-4 py-3 text-sm">
      {loading ? (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden />
      ) : reachable ? (
        <CheckCircle2 className="h-5 w-5 text-success" aria-hidden />
      ) : (
        <XCircle className="h-5 w-5 text-destructive" aria-hidden />
      )}
      <div className="flex flex-col">
        <span className="font-medium">
          {loading
            ? "Checking agents service…"
            : reachable
              ? "agents service reachable"
              : "agents service unreachable"}
        </span>
        <span className={cn("font-mono text-xs text-muted-foreground")}>
          {loading
            ? "GET /api/agents/health"
            : reachable
              ? `${result?.agents?.service} v${result?.agents?.version} · ${result?.agents?.status}`
              : (result?.error ?? "unknown error")}
        </span>
      </div>
    </div>
  );
}
