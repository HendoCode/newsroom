import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// shadcn/ui button — variants defined with class-variance-authority against SEMANTIC TOKENS
// only (bg-primary, bg-destructive, …). No brand hex here; re-skin via the tokens in globals.css.
// Disabled state is a flat, uniform "muted" look shared by every variant — deliberately not a
// translucent version of that variant's own color (cmw-interactive-state-affordance: measured
// that a 50%-opacity fade of e.g. bg-destructive/text-destructive-foreground still renders as a
// merely-paler destructive button, easy to mistake for an active, quieter variant, rather than an
// unambiguous "not clickable" signal). Collapsing to the same muted/foreground pair every time —
// with no variant-specific color left showing — is a signal no active variant can produce.
const DISABLED = "disabled:pointer-events-none disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground";

const buttonVariants = cva(
  `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${DISABLED} [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0`,
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/80",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/80",
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        // Bordered like `outline` (cmw-interactive-state-affordance: bg-secondary alone measured
        // 1.15:1/1.43:1 against the page background in light/dark — far under the 3:1 WCAG 1.4.11
        // boundary floor, i.e. a secondary button had no visible edge at all). --secondary itself
        // is untouched (it's deliberately a quieter fill than --primary); the border is what makes
        // it read as a bounded control.
        secondary:
          "border border-input bg-secondary text-secondary-foreground hover:bg-secondary/80 active:bg-secondary/70",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
