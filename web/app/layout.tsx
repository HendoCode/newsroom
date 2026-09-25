import type { Metadata } from "next";
import { Josefin_Sans, JetBrains_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

// Brand fonts (visual-identity.md §3), exposed as the CSS variables the Tailwind theme maps to.
// Loaded via next/font so they are self-hosted and swappable alongside the color tokens.
const josefin = Josefin_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["300", "700"]
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Content Machine",
  description: "Team harness around the content-machine agent (v1 skeleton).",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${josefin.variable} ${jetbrainsMono.variable} min-h-screen`}
      >
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
