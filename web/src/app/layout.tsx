// web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { cn } from "@/lib/utils";
import { ReactQueryProvider } from "@/providers/query-provider";
import { FirebaseClientProvider } from "@/firebase/client-provider";
import { AuthProvider } from "@/providers/auth-provider";
import { ServiceProvider } from "@/shared/contexts/ServiceContext";
import { Toaster } from "@/components/ui/toaster";
import "./globals.css";

const inter = localFont({
  src: [
    { path: "./fonts/Inter-400.ttf", weight: "400" },
    { path: "./fonts/Inter-500.ttf", weight: "500" },
    { path: "./fonts/Inter-600.ttf", weight: "600" },
    { path: "./fonts/Inter-700.ttf", weight: "700" },
    { path: "./fonts/Inter-800.ttf", weight: "800" },
    { path: "./fonts/Inter-900.ttf", weight: "900" },
  ],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "StockerPro — Smart Stock Analysis",
  description:
    "Track your favorite stocks, set price targets, and get instant alerts with StockerPro. Your ultimate tool for smart investing.",
};

export const viewport: Viewport = {
  themeColor: "#060914",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head />
      <body
        className={cn(
          "min-h-screen bg-background font-sans antialiased",
          inter.variable,
        )}
      >
        {/* Global page backdrop — renders behind everything */}
        <div className="app-backdrop" aria-hidden="true" />

        {/*
          Provider nesting order:
            ReactQueryProvider   — outermost: all child hooks get useQueryClient()
              FirebaseClientProvider
                AuthProvider
                  ServiceProvider
                    {children}

          ReactQueryProvider must be outside Firebase/Auth so those providers'
          own hooks can also benefit from query caching in the future.
        */}
        <ReactQueryProvider>
          <FirebaseClientProvider>
            <AuthProvider>
              <ServiceProvider>
                {children}
              </ServiceProvider>
            </AuthProvider>
          </FirebaseClientProvider>
        </ReactQueryProvider>

        <Toaster />
      </body>
    </html>
  );
}