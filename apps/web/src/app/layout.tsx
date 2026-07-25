import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { UserMenu } from "@/components/auth/user-menu";
import { Footer } from "@/components/footer";
import { HealthStatus } from "@/components/health-status";

import { Providers } from "./providers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ATIP — Automotive Technical Intelligence Platform",
  description: "Verified AI workspace for automotive compliance & engineering documents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* No-flash theme: apply persisted choice before hydration/paint. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('atip-theme');if(t==='dark'){document.documentElement.classList.add('dark');}else if(t==='light'){document.documentElement.classList.remove('dark');}}catch(e){}})();`,
          }}
        />
        <Providers>
          <header className="sticky top-0 z-40 border-b bg-card">
            <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-4 px-6">
              <Link href="/" className="flex min-w-0 items-baseline gap-3">
                <span className="font-serif text-lg font-semibold tracking-tight">ATIP</span>
                <span className="hidden truncate text-xs text-muted-foreground md:inline">
                  Automotive Technical Intelligence Platform
                </span>
              </Link>
              <div className="flex shrink-0 items-center gap-3">
                <HealthStatus />
                <UserMenu />
              </div>
            </div>
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
