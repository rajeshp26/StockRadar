import { NextRequest, NextResponse } from 'next/server';

/**
 * SECURE BRIDGE: Forwards browser requests to the Python backend on port 8000.
 * Logs everything to the IDE terminal for debugging.
 */

async function handleProxy(request: NextRequest, method: string, pathParts: string[]) {
  const path = pathParts.join('/');
  const targetUrl = `http://127.0.0.1:8000/${path}`;
  
  // Auth header is no longer needed as backend trusts the UID in the body
  // const authHeader = request.headers.get('Authorization');

  console.log(`[DEBUG] Bridge: Received ${method} for ${path}`);
  console.log(`[DEBUG] Bridge: Forwarding to ${targetUrl}`);

  try {
    const fetchOptions: RequestInit = {
      method: method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (method !== 'GET') { // Adjusted to allow body for POST, DELETE etc.
       const body = await request.json();
       fetchOptions.body = JSON.stringify(body);
       console.log(`[DEBUG] Bridge: Payload attached.`);
    }

    const response = await fetch(targetUrl, fetchOptions);
    console.log(`[DEBUG] Bridge: Backend responded with status ${response.status}`);

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });

  } catch (error: any) {
    console.error(`[DEBUG] Bridge FATAL Error:`, error.message);
    return NextResponse.json(
      { detail: 'Bridge failed to connect to backend', error: error.message },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'POST', (await params).path);
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'GET', (await params).path);
}

export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  // NOTE: DELETE requests with a body are unconventional but supported here for simplicity.
  return handleProxy(request, 'DELETE', (await params).path);
}
