// web/src/app/layout.tsx
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { cn } from "@/lib/utils";
import { FirebaseClientProvider } from "@/firebase/client-provider";
import { ServiceProvider } from "@/shared/contexts/ServiceContext";
import { AuthProvider } from "@/providers/auth-provider";
import { ReactQueryProvider } from "@/providers/query-provider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600", "700", "800", "900"],
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