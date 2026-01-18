import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Toaster } from '@/components/ui/toaster';
import { cn } from '@/lib/utils';
import { FirebaseClientProvider } from '@/firebase/client-provider';
import { ServiceProvider } from '@/shared/contexts/ServiceContext';
import { AuthProvider } from '@/providers/auth-provider';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });

export const metadata: Metadata = {
  title: 'StockerPro - Your Personal Stock Watchlist',
  description: 'Track your favorite stocks, set price targets, and get instant alerts with StockerPro. Your ultimate tool for smart investing.',
};

export const viewport: Viewport = {
  themeColor: '#3F51B5',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
      </head>
      <body className={cn('min-h-screen bg-background font-sans antialiased', inter.variable)}>
        <FirebaseClientProvider>
          <AuthProvider>
            <ServiceProvider>
              {children}
            </ServiceProvider>
          </AuthProvider>
        </FirebaseClientProvider>
        <Toaster />
      </body>
    </html>
  );
}
