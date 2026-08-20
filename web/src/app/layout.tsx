import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DemoBanner } from "@/components/demo-banner";
import { Nav } from "@/components/nav";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Personal Finance",
  description: "Net worth, balances, and spending.",
  // The real deployment must never be indexed. The demo is the opposite — it exists
  // to be found — and NEXT_PUBLIC_DEMO is a build-time value, so this resolves once
  // per build rather than per request.
  robots:
    process.env.NEXT_PUBLIC_DEMO === "true"
      ? { index: true, follow: true }
      : { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="bg-surface-0 text-ink flex min-h-full flex-col font-sans">
        <DemoBanner />
        <Nav />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
