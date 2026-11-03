import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "FINN | Financial Investment Agent",
  description: "Evidence-backed market monitoring and company research.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full font-sans antialiased">
        <Suspense fallback={<div className="min-h-screen bg-[#0b0e13]" />}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </body>
    </html>
  );
}
