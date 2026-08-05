import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * Public, read-only Supabase client for server-side data fetching.
 * This service has no login, so we only ever use the anon key and never
 * persist a session. Safe to import from Server Components.
 */
let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (client) return client;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    throw new Error(
      "Supabase 환경변수가 없습니다. frontend/.env.local 에 " +
        "NEXT_PUBLIC_SUPABASE_URL 과 NEXT_PUBLIC_SUPABASE_ANON_KEY 를 설정하세요."
    );
  }

  client = createClient(url, anonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return client;
}

/**
 * True when both Supabase env vars look real (URL must be an http(s) URL).
 * This guards against leftover placeholder text in .env.local so the app
 * cleanly falls back to dummy data until real keys are entered.
 */
export function isSupabaseConfigured(): boolean {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  return Boolean(url && key && /^https?:\/\//.test(url));
}
