import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/'

  if (code) {
    const cookieStore = await cookies()

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll()
          },
          setAll(cookiesToSet: { name: string; value: string; options?: any }[]) {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          },
        },
      }
    )

    const { data, error } = await supabase.auth.exchangeCodeForSession(code)

    if (!error && data.session) {
      const provider = data.session.user.app_metadata?.provider
      const email = data.session.user.email ?? ''

      if (provider && provider !== 'email') {
        return NextResponse.redirect(`${origin}/signup?step=3&email=${encodeURIComponent(email)}`)
      }

      if (data.session.user.email_confirmed_at) {
        return NextResponse.redirect(`${origin}/signup?verified=true&email=${encodeURIComponent(email)}`)
      }

      return NextResponse.redirect(`${origin}/signup?step=2&email=${encodeURIComponent(email)}`)
    }
  }

  return NextResponse.redirect(`${origin}/signup?error=auth_callback_failed`)
}
