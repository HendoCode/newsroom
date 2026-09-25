import * as React from "react";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * The one error/warning/success/info banner every screen should use (cmw-first-run-ux-batch item
 * 1) — variants against SEMANTIC TOKENS only (bg-destructive, bg-warning, …), matching the
 * button/badge convention. Before this, ~16 call sites hand-rolled `<p role="alert" ...>`/
 * `<div role="alert" ...>` with drifting classNames (some with no border/bg at all) — this
 * consolidates them into one visual language site-wide.
 */
const alertVariants = cva(
  "flex items-start gap-2 rounded-md border px-3 py-2 text-sm [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        destructive: "border-destructive/40 bg-destructive/10 text-destructive",
        warning: "border-warning/40 bg-warning/10 text-warning",
        success: "border-success/40 bg-success/10 text-success",
        info: "border-info/40 bg-info/10 text-info",
      },
    },
    defaultVariants: {
      variant: "destructive",
    },
  },
);

const ALERT_ICONS = {
  destructive: AlertTriangle,
  warning: AlertTriangle,
  success: CheckCircle2,
  info: Info,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

/** `role="alert"` fits destructive/warning (assertive, needs attention); success/info stay `role="status"`. */
function Alert({ className, variant = "destructive", children, ...props }: AlertProps) {
  const Icon = ALERT_ICONS[variant ?? "destructive"];
  return (
    <div
      role={variant === "destructive" || variant === "warning" ? "alert" : "status"}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      <Icon aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export { Alert, alertVariants };
