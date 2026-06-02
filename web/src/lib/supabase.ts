import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

// Singleton: all consumers share one GoTrueClient instance so that
// onAuthStateChange subscribers (AuthProvider) and callers of
// signInWithPassword (LoginForm) fire events on the same event emitter.
let _client: SupabaseClient | null = null;

export function createClient(): SupabaseClient {
  if (!_client) {
    _client = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
  }
  return _client;
}

// Expose for testing / reset
export function _resetClient(): void {
  _client = null;
}
