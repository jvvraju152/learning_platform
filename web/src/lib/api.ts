import { useEffect, useState } from "react"

export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { credentials: "same-origin" }
  if (body !== undefined) {
    opts.method = "POST"
    opts.headers = { "Content-Type": "application/json" }
    opts.body = JSON.stringify(body)
  }
  const res = await fetch("/api" + path, opts)
  let data: any = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) throw new Error(data?.detail || `Something went wrong (${res.status}).`)
  return data
}

/** GET helper: { data, error, loading } */
export function useApi<T = any>(path: string | null) {
  const [state, set] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: "", loading: !!path })
  useEffect(() => {
    if (!path) return
    let live = true
    set({ data: null, error: "", loading: true })
    api<T>(path).then(
      (data) => live && set({ data, error: "", loading: false }),
      (e) => live && set({ data: null, error: e.message, loading: false }))
    return () => { live = false }
  }, [path])
  return state
}

export const pct = (x?: number | null) => (x == null ? "-" : Math.round(x * 100) + "%")
export const LEVEL: Record<string, string> = { easy: "Easy", medium: "Medium", hard: "Hard", practice: "Practice" }
export const STATUS: Record<string, string> = {
  weak: "Weak", developing: "Developing", strong: "Strong", insufficient_data: "Not enough answers",
  stale: "Re-test", not_started: "Not started",
}
