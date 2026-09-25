import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// shadcn/ui badge — variants against SEMANTIC TOKENS only (no brand hex; re-skin via globals.css).
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        muted: "border-transparent bg-muted text-muted-foreground",
        warning: "border-transparent bg-warning/15 text-warning",
        // Solid fill, not the translucent warning/muted pattern above — `accent`/`accent-foreground`
        // is only measured-safe (cmw-interactive-state-affordance) as a solid-on-solid pairing, not
        // text-on-tinted-panel (unlike warning/success/info, which were darkened specifically for
        // that pairing). Reserve for emphasis that needs equal visual weight to a primary button
        // (the Pipeline redesign's loop-round chip and pending-lessons chip).
        accent: "border-transparent bg-accent text-accent-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
