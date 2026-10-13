import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react"
import { HashRouter, Routes, Route, Navigate, Outlet, Link, matchPath, useLocation, useNavigate } from "react-router-dom"
import { BarChart3, BookOpen, ChevronLeft, GraduationCap, LogOut } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import Auth from "@/pages/Auth"

// Pages load on demand so the login screen and shell stay small.
const Subjects = lazy(() => import("@/pages/Learn").then((m) => ({ default: m.Subjects })))
const Modules = lazy(() => import("@/pages/Learn").then((m) => ({ default: m.Modules })))
const Module = lazy(() => import("@/pages/Learn").then((m) => ({ default: m.Module })))
const Quiz = lazy(() => import("@/pages/Quiz"))
const Dashboard = lazy(() => import("@/pages/Dashboard"))

// "Subjects" stays highlighted on every learning page (subject, module, quiz), not just /subjects.
const NAV = [
  { to: "/subjects", label: "Subjects", Icon: BookOpen, match: /^\/(subjects?|module|quiz)(\/|$)/ },
  { to: "/progress", label: "My Progress", Icon: BarChart3, match: /^\/progress$/ },
]
const STAGES = [["easy", "Beginner"], ["medium", "Intermediate"], ["hard", "Advanced"], ["practice", "Practice"]]

const pill = (active: boolean) =>
  cn("shrink-0 rounded-full border px-3 py-1 font-medium transition-colors",
    active ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground")

function Layout() {
  const [user, setUser] = useState<any>(undefined)
  const { pathname } = useLocation()
  const nav = useNavigate()
  const checked = useRef("")
  const load = useCallback(() => api("/me").then((r) => (r.user ? setUser(r.user) : nav("/login", { replace: true })), () => nav("/login", { replace: true })), [nav])

  useEffect(() => { load() }, [load])
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])

  // Opening a subject adds it to "My subjects": refresh the user once per subject so the chips stay current.
  const subject = matchPath("/subject/:subject", pathname)?.params.subject
  useEffect(() => {
    if (subject && user && subject !== checked.current && !(user.subjects ?? []).includes(subject)) { checked.current = subject; load() }
  }, [subject, user, load])

  if (!user) return <div role="status" className="p-10 text-center text-muted-foreground">Loading...</div>

  const quiz = matchPath("/quiz/:topic/:level", pathname)?.params
  const mySubjects: string[] = user.subjects ?? []
  const logout = () => api("/logout", {}).catch(() => {}).finally(() => nav("/login"))

  return (
    <div className="min-h-screen">
      <button className="sr-only fixed left-2 top-2 z-30 rounded-md bg-card px-3 py-2 text-sm focus:not-sr-only" onClick={() => document.getElementById("main")?.focus()}>Skip to content</button>

      <header className="sticky top-0 z-20 border-b bg-card/90 backdrop-blur">
        <div className="container flex h-14 items-center gap-2">
          <Link to="/subjects" className="mr-2 flex items-center gap-2 font-semibold sm:mr-4"><GraduationCap className="h-5 w-5 text-primary" aria-hidden />LearnMate</Link>
          <nav aria-label="Main" className="hidden gap-1 sm:flex">
            {NAV.map(({ to, label, Icon, match }) => {
              const on = match.test(pathname)
              return (
                <Link key={to} to={to} aria-current={on ? "page" : undefined}
                  className={cn("flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors", on ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground")}>
                  <Icon className="h-4 w-4" aria-hidden />{label}
                </Link>
              )
            })}
          </nav>
          <span className="ml-auto hidden text-sm text-muted-foreground sm:block">{user.name}</span>
          <Button variant="ghost" size="sm" className="ml-auto sm:ml-0" onClick={logout} aria-label="Log out"><LogOut className="h-4 w-4" aria-hidden /><span className="hidden sm:inline">Log out</span></Button>
        </div>

        {quiz ? (
          <nav aria-label="Learning stages" className="container flex items-center gap-2 overflow-x-auto pb-2 text-sm [scrollbar-width:none]">
            <Link to={`/module/${quiz.topic}`} className="flex shrink-0 items-center gap-0.5 rounded-full px-2 py-1 font-medium text-muted-foreground hover:text-foreground"><ChevronLeft className="h-4 w-4" aria-hidden />Module</Link>
            <span aria-hidden className="h-4 w-px shrink-0 bg-border" />
            {STAGES.map(([id, label]) => <Link key={id} to={`/quiz/${quiz.topic}/${id}`} aria-current={id === quiz.level ? "page" : undefined} className={pill(id === quiz.level)}>{label}</Link>)}
          </nav>
        ) : mySubjects.length > 0 && (
          <nav aria-label="My subjects" className="container flex items-center gap-2 overflow-x-auto pb-2 text-sm [scrollbar-width:none]">
            <span className="shrink-0 text-xs text-muted-foreground">My subjects</span>
            {mySubjects.map((s) => <Link key={s} to={`/subject/${encodeURIComponent(s)}`} aria-current={s === subject ? "page" : undefined} className={pill(s === subject)}>{s}</Link>)}
          </nav>
        )}
      </header>

      <main id="main" tabIndex={-1} className="container py-6 pb-24 outline-none sm:py-8 sm:pb-8">
        <Suspense fallback={<p role="status" className="text-muted-foreground">Loading...</p>}><Outlet context={{ user }} /></Suspense>
      </main>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-20 flex border-t bg-card pb-[env(safe-area-inset-bottom)] sm:hidden">
        {NAV.map(({ to, label, Icon, match }) => {
          const on = match.test(pathname)
          return (
            <Link key={to} to={to} aria-current={on ? "page" : undefined}
              className={cn("relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs font-medium", on ? "text-primary before:absolute before:inset-x-8 before:top-0 before:h-0.5 before:rounded-full before:bg-primary" : "text-muted-foreground")}>
              <Icon className="h-5 w-5" aria-hidden />{label}
            </Link>
          )
        })}
      </nav>
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Auth mode="login" />} />
        <Route path="/signup" element={<Auth mode="signup" />} />
        <Route element={<Layout />}>
          <Route path="/subjects" element={<Subjects />} />
          <Route path="/subject/:subject" element={<Modules />} />
          <Route path="/module/:topic" element={<Module />} />
          <Route path="/quiz/:topic/:level" element={<Quiz />} />
          <Route path="/progress" element={<Dashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/subjects" replace />} />
      </Routes>
    </HashRouter>
  )
}
