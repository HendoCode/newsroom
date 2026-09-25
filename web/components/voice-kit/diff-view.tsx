"use client";

import { cn } from "@/lib/utils";
import { diffLines } from "@/lib/voice-kit/diff";

/** Renders a unified line diff — shared by the editor pane's "Diff vs current" and the version
 * history's "Compare" (cmw-ui-wireframes screen 11). */
export function DiffView({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after);
  return (
    <pre
      data-testid="diff-view"
      className="max-h-80 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs leading-relaxed"
    >
      {lines.map((line, i) => (
        <div
          key={i}
          className={cn(
            "whitespace-pre-wrap",
            line.type === "added" && "bg-success/15 text-foreground",
            line.type === "removed" && "bg-destructive/10 text-muted-foreground line-through",
          )}
        >
          {line.type === "added" ? "+ " : line.type === "removed" ? "- " : "  "}
          {line.text}
        </div>
      ))}
    </pre>
  );
}
