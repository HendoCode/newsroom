"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

// Wraps next-themes so light/dark is available app-wide from day one (class strategy → the
// `.dark` token set in globals.css). Downstream tickets add more themes by adding token sets.
export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
