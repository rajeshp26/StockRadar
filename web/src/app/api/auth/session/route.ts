// web/src/app/api/auth/session/route.ts
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = process.env.PROXY_IDTOKEN_COOKIE ?? "__session";
// Align with your refresh cadence; 55-60 minutes is typical for Firebase ID tokens
const COOKIE_MAX_AGE = 60 * 60; // seconds

export async function POST(req: NextRequest) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    // ignore; will treat as empty body
  }

  const { idToken, action } = body || {};
  const res = NextResponse.json({ ok: true });

  // Choose secure flag based on the incoming request's URL scheme.
  const isHttps = req.nextUrl.protocol === "https:";
  const cookieBase = {
    httpOnly: true,
    secure: isHttps,            // always true if served over HTTPS
    sameSite: "lax" as const,   // robust for first-party subresource requests (incl. SSE)
    path: "/",
  };

  // Clear cookie
  if (action === "clear" || !idToken) {
    res.cookies.set({
      name: COOKIE_NAME,
      value: "",
      ...cookieBase,
      maxAge: 0,
    });
    return res;
  }

  if (typeof idToken !== "string" || idToken.length < 20) {
    return NextResponse.json(
      { ok: false, error: "Invalid token" },
      { status: 400 }
    );
  }

  // (Optional but recommended) Verify the token here for defense-in-depth:
  // import { getAuth } from "firebase-admin/auth";
  // await getAuth().verifyIdToken(idToken, /* checkRevoked= */true);

  // Mint cookie
  res.cookies.set({
    name: COOKIE_NAME,
    value: idToken,
    ...cookieBase,
    maxAge: COOKIE_MAX_AGE,
  });

  return res;
}