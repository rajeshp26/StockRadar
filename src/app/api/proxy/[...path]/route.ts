import { NextRequest, NextResponse } from 'next/server';

/**
 * SECURE BRIDGE: Forwards browser requests to the Python backend on port 8001.
 * Supports standard JSON and Server-Sent Events (SSE) streaming.
 */

async function handleProxy(request: NextRequest, method: string, pathParts: string[]) {
  const { searchParams } = new URL(request.url);
  const path = pathParts.join('/');
  const queryString = searchParams.toString();
  
  // Changed port from 8000 to 8001 and using 127.0.0.1
  const targetUrl = `http://127.0.0.1:8001/${path}${queryString ? `?${queryString}` : ''}`;

  console.log(`[DEBUG] Bridge: Received ${method} for ${path} -> Forwarding to ${targetUrl}`);

  try {
    const fetchOptions: RequestInit = {
      method: method,
      headers: {
        'Accept': request.headers.get('Accept') || 'application/json',
      },
    };

    if (method !== 'GET') {
      const contentLength = request.headers.get('content-length');
      if (contentLength && parseInt(contentLength) > 0) {
        const body = await request.json();
        fetchOptions.body = JSON.stringify(body);
        fetchOptions.headers = { ...fetchOptions.headers, 'Content-Type': 'application/json' };
      }
    }

    const response = await fetch(targetUrl, fetchOptions);

    // Handle Streaming Responses (SSE)
    if (response.headers.get('content-type')?.includes('text/event-stream')) {
      console.log(`[DEBUG] Bridge: Detected EventStream from backend for ${path}`);
      
      const stream = new ReadableStream({
        async start(controller) {
          if (!response.body) {
            controller.close();
            return;
          }
          const reader = response.body.getReader();
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              controller.enqueue(value);
            }
          } catch (error) {
            console.error('[DEBUG] Bridge: Stream error:', error);
          } finally {
            controller.close();
            reader.releaseLock();
          }
        },
      });

      return new Response(stream, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // Handle standard JSON or Text responses
    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    } else {
      const textData = await response.text();
      return new NextResponse(textData, { 
        status: response.status, 
        headers: { 'Content-Type': contentType || 'text/plain' } 
      });
    }

  } catch (error: any) {
    console.error(`[DEBUG] Bridge FATAL Error reaching backend:`, error.message);
    return NextResponse.json(
      { detail: 'Bridge encountered an unexpected error', error: error.message, target: targetUrl },
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
  return handleProxy(request, 'DELETE', (await params).path);
}

export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return handleProxy(request, 'PATCH', (await params).path);
}
