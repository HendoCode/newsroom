import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("merges and de-conflicts tailwind classes", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", false && "hidden", "font-medium")).toBe("text-sm font-medium");
  });
});

describe("Button", () => {
  it("renders its label", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("uses only semantic token classes, never a brand hex literal", () => {
    const classes = buttonVariants({ variant: "default" });
    // Token-driven design foundation: no raw hex/hsl values leak into component classes.
    expect(classes).toContain("bg-primary");
    expect(classes).not.toMatch(/#[0-9a-fA-F]{3,6}/);
    expect(classes).not.toMatch(/hsl\(/);
  });
});
