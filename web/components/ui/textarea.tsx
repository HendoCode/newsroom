import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn/ui textarea — token-driven surface (bg-background / border-input / ring-ring), the
// multiline sibling of `components/ui/input.tsx`. Same recipe and disabled-treatment discipline
// as `Input`/`Button` (a flat "muted" collapse, not a translucent fade — cmw-interactive-state-
// affordance), so the two text fields render as one family.
const TextArea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    className={cn(
      "flex min-h-20 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground",
      className,
    )}
    ref={ref}
    {...props}
  />
));
TextArea.displayName = "TextArea";

export { TextArea };
