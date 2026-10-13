import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, BookOpen, CheckCircle2, Clock, ExternalLink, ListChecks, Pencil } from "lucide-react"
import { api, useApi, pct, STATUS } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loading, MasteryBar, StatusPill, Trend, toneOf } from "@/pages/Learn"

const TASK_ICON: Record<string, any> = { learn: BookOpen, practice: Pencil }

/** Overall mastery: the ring draws in once on load. */
function MasteryRing({ value }: { value: number }) {
  const [on, setOn] = useState(false)
  useEffect(() => { const id = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(id) }, [])
  const R = 52, C = 2 * Math.PI * R, v = Math.max(0, Math.min(1, value || 0))
  return (
    <div className="relative h-32 w-32 shrink-0" role="img" aria-label={`Overall mastery ${pct(v)}`}>
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden>
        <circle cx="60" cy="60" r={R} fill="none" strokeWidth="10" className="ring-track" />
        <circle cx="60" cy="60" r={R} fill="none" strokeWidth="10" className="ring-arc" strokeDasharray={C} strokeDashoffset={on ? C * (1 - v) : C} style={{ opacity: v === 0 ? 0 : 1 }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold leading-none tabular-nums">{pct(v)}</span>
        <span className="mt-1 text-xs text-muted-foreground">mastery</span>
      </div>
    </div>
  )
}

function Stat({ icon: Icon, tone, label, value }: { icon: any; tone: "neutral" | "strong" | "weak" | "muted"; label: string; value: number }) {
  return (
    <Card className="card-raised">
      <CardContent className="flex items-center gap-4 p-4">
        <span className="tone-tile" data-tone={tone}><Icon className="h-5 w-5" aria-hidden /></span>
        <div><div className="text-sm text-muted-foreground">{label}</div><div className="text-2xl font-bold tabular-nums">{value}</div></div>
      </CardContent>
    </Card>
  )
}

function Plan() {
  const [days, setDays] = useState(7), [mins, setMins] = useState(60)
  const [plan, setPlan] = useState<any>(null), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [stamp, setStamp] = useState(0)
  const make = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(""); setBusy(true)
    try { setPlan(await api(`/me/plan?days=${days}&minutes=${mins}`)); setStamp((s) => s + 1) }
    catch (x: any) { setErr(x.message) }
    finally { setBusy(false) }
  }
  const hasDays = plan && plan.days.length > 0
  return (
    <Card className="card-raised">
      <CardHeader><CardTitle>Study plan</CardTitle><CardDescription>A day-by-day plan built from your weak topics.</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <form onSubmit={make} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-2"><Label htmlFor="d">Days (2 to 30)</Label><Input id="d" type="number" min={2} max={30} className="w-full sm:w-28" value={days} onChange={(e) => setDays(+e.target.value)} /></div>
          <div className="space-y-2"><Label htmlFor="m">Minutes per day (20 to 480)</Label><Input id="m" type="number" min={20} max={480} className="w-full sm:w-40" value={mins} onChange={(e) => setMins(+e.target.value)} /></div>
          <Button disabled={busy}>{busy ? "Making plan..." : "Make plan"}</Button>
        </form>
        {err && <p role="alert" className="feedback" data-tone="weak"><AlertTriangle className="h-4 w-4" aria-hidden /><span>{err}</span></p>}
        {hasDays && <p key={stamp} role="status" className="feedback feedback-pop" data-tone="strong"><CheckCircle2 className="h-4 w-4" aria-hidden /><span>Plan made: {plan.days.length} days, {plan.total_minutes} minutes in total.</span></p>}
        {plan && !plan.days.length && <p className="text-sm text-muted-foreground">{plan.message}</p>}
        {hasDays && (
          <div className="grid gap-3 md:grid-cols-2">
            {plan.days.map((d: any) => (
              <div key={d.day} className="rounded-xl border p-4">
                <div className="mb-3 flex items-center gap-2"><Badge>Day {d.day}</Badge><span className="font-medium">{d.topic_name}</span></div>
                <ul className="space-y-3 text-sm">
                  {d.tasks.map((k: any, i: number) => {
                    const Icon = TASK_ICON[k.type] || Clock
                    return (
                      <li key={i} className="flex items-start gap-3">
                        <span className="tone-tile tone-tile-sm" data-tone="neutral"><Icon className="h-4 w-4" aria-hidden /></span>
                        <div className="min-w-0 flex-1">
                          <div className="flex justify-between gap-2"><b className="capitalize">{k.type}</b><span className="text-xs tabular-nums text-muted-foreground">{k.minutes} min</span></div>
                          <div className="text-muted-foreground">
                            {k.type === "learn" ? (k.resource ? <a className="text-primary underline" href={k.resource.url} target="_blank" rel="noopener noreferrer">{k.resource.title}</a> : "Read your notes") : k.type === "practice" ? `About ${k.questions} questions` : k.note}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function Dashboard() {
  const a = useApi("/me/analysis"), r = useApi("/me/recommendations")
  if (!a.data) return <Loading error={a.error} loading={a.loading} />
  const d = a.data
  if (!d.topics.length) return (
    <Card className="card-raised"><CardContent className="space-y-3 p-8 text-center"><p className="text-muted-foreground">You have not answered any questions yet.</p><Button asChild><Link to="/subjects">Choose a subject and take a quiz</Link></Button></CardContent></Card>
  )

  const count = (s: string) => d.topics.filter((t: any) => t.status === s).length
  const strong = count("strong"), weak = count("weak"), developing = count("developing")
  const dist = ["strong", "developing", "weak", "insufficient_data"].map((s) => [s, count(s)] as [string, number]).filter(([, n]) => n > 0)
  const headline = weak > 0 ? `${weak} ${weak === 1 ? "topic needs" : "topics need"} attention first.`
    : developing > 0 ? "No weak topics. Keep building the developing ones."
    : strong === d.topics.length ? "Every topic you have practiced is strong."
    : "Keep answering questions to firm up your estimates."
  const recs = r.data?.recommendations
  const nothingToFix = d.weak_topics.length === 0 && d.developing_topics.length === 0 && strong > 0

  return (
    <div className="space-y-8">
      <section className="hero card-raised">
        <div className="flex flex-col items-center gap-6 p-6 text-center sm:flex-row sm:p-8 sm:text-left">
          <MasteryRing value={d.overall_mastery} />
          <div className="min-w-0 flex-1 space-y-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">My progress</h1>
              <p className="mt-1 text-muted-foreground">{headline}</p>
            </div>
            <div className="space-y-2">
              <div className="seg-bar" role="img" aria-label={dist.map(([s, n]) => `${n} ${STATUS[s] || s}`).join(", ")}>
                {dist.map(([s, n]) => <span key={s} className="seg" data-tone={toneOf(s)} style={{ flexGrow: n }} />)}
              </div>
              <ul className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm sm:justify-start">
                {dist.map(([s, n]) => <li key={s} data-tone={toneOf(s)} className="inline-flex items-center gap-1.5"><span className="dot" aria-hidden /><b className="tabular-nums">{n}</b> {STATUS[s] || s}</li>)}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat icon={ListChecks} tone="neutral" label="Questions answered" value={d.data_quality.rows_used} />
        <Stat icon={CheckCircle2} tone="strong" label="Strong topics" value={strong} />
        <Stat icon={AlertTriangle} tone={weak > 0 ? "weak" : "muted"} label="Weak topics" value={weak} />
      </div>

      {Object.keys(d.subject_mastery).length > 0 && (
        <Card className="card-raised"><CardHeader><CardTitle>By subject</CardTitle></CardHeader><CardContent className="space-y-5">
          {Object.entries(d.subject_mastery).map(([s, v]: any) => (
            <div key={s}><div className="mb-1.5 flex justify-between text-sm"><span className="font-medium">{s}</span><span className="tabular-nums text-muted-foreground">{pct(v)}</span></div><MasteryBar large value={v} label={`${s} mastery`} /></div>
          ))}
        </CardContent></Card>
      )}

      <Card className="card-raised">
        <CardHeader><CardTitle>Topics</CardTitle><CardDescription>Mastery is an estimate: recent answers count more, and with few answers it stays near 50%.</CardDescription></CardHeader>
        <CardContent>
          <ul className="divide-y">
            {d.topics.map((t: any) => {
              const enough = t.status !== "insufficient_data"
              return (
                <li key={t.topic_id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 py-4 sm:grid-cols-[minmax(0,1fr)_10rem_auto_auto]">
                  <div className="order-1 min-w-0 sm:order-none">
                    <Link className="font-medium hover:text-primary" to={`/module/${t.topic_id}`}>{t.name}</Link>
                    <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                      <span>{t.subject}</span><span>{t.attempts} answered</span><span>Accuracy {pct(t.accuracy)}</span>{enough && <Trend trend={t.trend} />}
                    </div>
                  </div>
                  <div className="order-2 sm:order-none"><StatusPill status={t.status} /></div>
                  <div className="order-3 col-span-2 sm:order-none sm:col-span-1">
                    {enough ? (
                      <div className="flex items-center gap-3"><div className="flex-1"><MasteryBar value={t.mastery} tone={toneOf(t.status)} label={`${t.name} mastery`} /></div><span className="w-10 text-right text-sm font-semibold tabular-nums">{pct(t.mastery)}</span></div>
                    ) : <span className="text-xs text-muted-foreground">Needs more answers</span>}
                  </div>
                  <Button size="sm" variant="outline" className="order-4 col-span-2 w-full sm:order-none sm:col-span-1 sm:w-auto" asChild><Link to={`/quiz/${t.topic_id}/practice`}>Practice</Link></Button>
                </li>
              )
            })}
          </ul>
          {d.untested_topics.length > 0 && (
            <div className="mt-2 border-t pt-4">
              <p className="mb-2 text-xs text-muted-foreground">Not attempted yet</p>
              <div className="flex flex-wrap gap-2">{d.untested_topics.map((id: string) => <Link key={id} to={`/module/${id}`} className="rounded-full border px-3 py-1 text-xs hover:bg-muted">{d.topic_names[id] || id}</Link>)}</div>
            </div>
          )}
        </CardContent>
      </Card>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">What to work on</h2>
        {r.loading && !recs && <div className="h-24 animate-pulse rounded-xl bg-muted" aria-hidden />}
        {r.error && <p role="alert" className="text-sm text-destructive">{r.error}</p>}
        {recs && recs.length === 0 && (nothingToFix
          ? <p role="status" className="feedback" data-tone="strong"><CheckCircle2 className="h-4 w-4" aria-hidden /><span>Nothing to fix right now. None of your topics are weak or developing.</span></p>
          : <p className="text-sm text-muted-foreground">No weak or developing topics yet. Answer at least 3 questions per topic to get recommendations.</p>)}
        <div className="grid gap-4 md:grid-cols-2">
          {recs?.map((x: any) => {
            const wk = d.weak_topics.find((t: any) => t.topic_id === x.topic_id)
            const wt = wk || d.developing_topics.find((t: any) => t.topic_id === x.topic_id)
            return (
              <Card key={x.topic_id} className="card-raised flex flex-col">
                <CardHeader className="space-y-3">
                  <div className="flex items-start justify-between gap-3"><CardTitle className="text-base">{x.name}</CardTitle><span className="text-sm font-semibold tabular-nums">{pct(x.mastery)}</span></div>
                  <MasteryBar value={x.mastery} tone={wk ? "weak" : "developing"} label={`${x.name} mastery`} />
                  <CardDescription>Start with {x.level} material.</CardDescription>
                  {wt?.root_cause_for?.length > 0 && <p className="feedback" data-tone="developing"><AlertTriangle className="h-4 w-4" aria-hidden /><span>A prerequisite for other weak topics, so fix it first.</span></p>}
                </CardHeader>
                <CardContent className="mt-auto space-y-3">
                  <ul className="space-y-2 text-sm">{x.resources.map((u: any) => (<li key={u.url}><a className="inline-flex items-center gap-1 text-primary hover:underline" href={u.url} target="_blank" rel="noopener noreferrer">{u.title}<ExternalLink className="h-3 w-3" aria-hidden /></a> <span className="block text-xs text-muted-foreground">{u.type}, {u.minutes} min, {u.provider}</span></li>))}</ul>
                  <Button size="sm" asChild><Link to={`/quiz/${x.topic_id}/practice`}>Practice this topic</Link></Button>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </section>
      <Plan />
    </div>
  )
}
