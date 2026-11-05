import type { Metadata } from "next";
import localFont from "next/font/local";

import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

// Brand fonts (visual-identity.md §3), exposed as the CSS variables the Tailwind theme maps to.
// Vendored in app/fonts/ (Google Fonts' latin-subset variable files, SIL OFL — licenses alongside)
// and loaded with next/font/local rather than next/font/google: the google loader fetches CSS from
// fonts.googleapis.com at *build* time, which made `npm run build` fail offline and flake when
// that fetch returned an unexpected response. Josefin Sans was previously loaded at weights
// 300 and 700; the variable file covers both (and everything between).
const josefin = localFont({
  src: "./fonts/josefin-sans-latin-var.woff2",
  weight: "100 700",
  variable: "--font-sans",
  display: "swap",
});
const jetbrainsMono = localFont({
  src: "./fonts/jetbrains-mono-latin-var.woff2",
  weight: "100 800",
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Newsroom",
  description: "Team harness around the newsroom agent (v1 skeleton).",
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
