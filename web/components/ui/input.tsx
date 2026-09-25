import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui input — token-driven surface (bg-background / border-input / ring-ring). No brand
// hex here; re-skin via the tokens in globals.css.
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        // Disabled: the same flat "collapse to muted" signal as Button (cmw-interactive-state-affordance)
        // rather than a translucent fade of the enabled look — see that component's DISABLED comment.
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
