"use client";

import { useAuth } from '@/providers/auth-provider';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { perf } from '@/lib/performance'; // Import the performance utility

// A simple full-page loading spinner component
function FullPageSpinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="h-16 w-16 animate-spin rounded-full border-b-2 border-t-2 border-primary"></div>
    </div>
  );
}

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.replace('/login');
    }

    if (status === 'authenticated') {
      // Mark the start of the render process from React's perspective.
      perf.mark('layout-render-start');
      
      // Use requestAnimationFrame to wait for the next browser paint.
      requestAnimationFrame(() => {
        perf.mark('layout-render-end');
        perf.measure('Layout Render', 'layout-render-start', 'layout-render-end');
      });
    }
  }, [status, router]);

  if (status === 'initializing') {
    return <FullPageSpinner />;
  }

  if (status === 'authenticated') {
    return <>{children}</>;
  }
  
  return null; // Render nothing for unauthenticated/error states while redirecting
}
