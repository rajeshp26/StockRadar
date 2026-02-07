'use client';

import { useAuth } from "@/providers/auth-provider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Header } from "@/components/header";

function FullPageSpinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="h-16 w-16 animate-spin rounded-full border-b-2 border-gray-900"></div>
    </div>
  );
}

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === 'unauthenticated' || status === 'error') router.push('/login');
  }, [status, router]);
  
  if (status === 'initializing' || status === 'unauthenticated' || status === 'error') {
    return <FullPageSpinner />;
  }

  if (status === "authenticated") {
    return (
      <div className="relative flex min-h-screen flex-col">
        <Header />
        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>
    );
  }

  return null;
}
