import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function proxy(request: NextRequest) {
  const url = request.nextUrl;

  // Log specific requests we are interested in to debug the issue
  if (url.pathname === '/manifest.json' || url.pathname.includes('forwardAuthCookie')) {
    const ip = request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip') || 'unknown';
    
    console.log('[Middleware] ----------------------------------------------------------------');
    console.log(`[Middleware] Request: ${request.method} ${url.pathname}`);
    console.log('[Middleware] Headers:', Object.fromEntries(request.headers));
    console.log(`[Middleware] IP: ${ip}`);
    console.log('[Middleware] ----------------------------------------------------------------');
  }

  return NextResponse.next();
}

export const config = {
  matcher: '/:path*',
};