import { NextRequest, NextResponse } from 'next/server';

/**
 * SECURE BRIDGE: Forwards browser requests to the Python backend on port 8001.
 * Supports standard JSON and includes Security: Forwarding Authorization headers.
 */

async function handleProxy(request: NextRequest, method: string, pathParts: string[]) {
  const { searchParams } = new URL(request.url);
  const path = pathParts.join('/');
  const queryString = searchParams.toString();
  const targetUrl = `http://127.0.0.1:8001/${path}${queryString ? `?${queryString}` : ''}`;

  const authHeader = request.headers.get('Authorization');
  console.log(`[PROXY DEBUG] ${method} /${path} | Auth Header Present: ${!!authHeader}`);
  if (authHeader) {
      console.log(`[PROXY DEBUG] Token starts with: ${authHeader.substring(0, 20)}...`);
  }

  try {
    const fetchOptions: RequestInit = {
      method: method,
      headers: {
        'Accept': request.headers.get('Accept') || 'application/json',
        // SECURITY: Forward the Authorization header (Bearer Token) to the backend
        'Authorization': authHeader || '',
      },
    };

    if (method !== 'GET' && method !== 'DELETE') {
      try {
        const body = await request.json();
        fetchOptions.body = JSON.stringify(body);
        fetchOptions.headers = { ...fetchOptions.headers, 'Content-Type': 'application/json' };
      } catch (e) {
        // No body or not JSON
      }
    }

    const response = await fetch(targetUrl, fetchOptions);
    console.log(`[PROXY DEBUG] Backend Response Status: ${response.status} for ${path}`);

    // Handle standard responses
    if (response.status === 204) return new NextResponse(null, { status: 204 });

    const contentType = response.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    } else {
      const textData = await response.text();
      return new NextResponse(textData, { status: response.status, headers: { 'Content-Type': contentType || 'text/plain' } });
    }

  } catch (error: any) {
    console.error(`[PROXY DEBUG] Bridge FATAL Error reaching backend:`, error.message);
    return NextResponse.json({ detail: 'Bridge encountered an unexpected error', error: error.message }, { status: 502 });
  }
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  const resolvedParams = await params;
  return handleProxy(request, 'POST', resolvedParams.path);
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  const resolvedParams = await params;
  return handleProxy(request, 'GET', resolvedParams.path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  const resolvedParams = await params;
  return handleProxy(request, 'DELETE', resolvedParams.path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  const resolvedParams = await params;
  return handleProxy(request, 'PATCH', resolvedParams.path);
}
