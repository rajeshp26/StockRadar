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
  console.log(`[DEBUG] Bridge: Attempting to forward to ${targetUrl}`);

  try {
    const controller = new AbortController();
    // Set a timeout for the fetch request to the backend (e.g., 10 seconds)
    const timeoutId = setTimeout(() => controller.abort(), 10000); 

    const fetchOptions: RequestInit = {
      method: method,
      headers: {
        'Content-Type': 'application/json',
      },
      signal: controller.signal, // Apply the abort controller's signal
    };

    if (method !== 'GET') { // Adjusted to allow body for POST, DELETE etc.
       // Check if there is a body before trying to parse JSON
       const contentLength = request.headers.get('content-length');
       if (contentLength && parseInt(contentLength) > 0) {
         const body = await request.json();
         fetchOptions.body = JSON.stringify(body);
         console.log(`[DEBUG] Bridge: Payload attached.`);
       } else {
         console.log(`[DEBUG] Bridge: No payload for non-GET request.`);
       }
    }

    const response = await fetch(targetUrl, fetchOptions);
    clearTimeout(timeoutId); // Clear the timeout if fetch completes in time
    console.log(`[DEBUG] Bridge: Backend responded with status ${response.status} for ${targetUrl}`);

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    // Ensure we only try to parse JSON if the content-type is json and there's a body
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    } else {
      const textData = await response.text();
      console.log(`[DEBUG] Bridge: Non-JSON response from backend. Status: ${response.status}, Content: ${textData.substring(0, 100)}...`);
      return new NextResponse(textData, { status: response.status, headers: { 'Content-Type': contentType || 'text/plain' } });
    }

  } catch (error: any) {
    // console.error(`[DEBUG] Bridge FATAL Error:`, error.message);
    // More detailed error logging
    if (error.name === 'AbortError') {
      console.error(`[DEBUG] Bridge FATAL Error: Fetch to ${targetUrl} timed out after 10 seconds.`);
      return NextResponse.json(
        { detail: 'Backend did not respond in time', error: 'Gateway Timeout' },
        { status: 504 }
      );
    } else if (error.cause && error.cause.code === 'ECONNREFUSED') {
      console.error(`[DEBUG] Bridge FATAL Error: Connection to backend at ${targetUrl} refused. Is the Python backend running and accessible?`);
      return NextResponse.json(
        { detail: 'Bridge could not connect to backend', error: 'Connection Refused' },
        { status: 502 }
      );
    } else {
      console.error(`[DEBUG] Bridge FATAL Error: An unexpected error occurred while forwarding to ${targetUrl}:`, error.message);
      return NextResponse.json(
        { detail: 'Bridge encountered an unexpected error', error: error.message },
        { status: 502 }
      );
    }
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
