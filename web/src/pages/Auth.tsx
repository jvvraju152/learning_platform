import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { GraduationCap } from "lucide-react"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function Auth({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup"
  const nav = useNavigate()
  const [f, setF] = useState({ name: "", email: "", password: "" })
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("")
    try { await api(signup ? "/register" : "/login", signup ? f : { email: f.email, password: f.password }); nav("/subjects") }
    catch (x: any) { setErr(x.message); setBusy(false) }
  }
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-accent via-background to-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground"><GraduationCap /></div>
          <CardTitle className="text-2xl">{signup ? "Create your account" : "Welcome back"}</CardTitle>
          <CardDescription>Short quizzes that find your weak topics and tell you what to study next.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {signup && <div className="space-y-2"><Label htmlFor="name">Your name</Label><Input id="name" maxLength={60} required value={f.name} onChange={set("name")} /></div>}
            <div className="space-y-2"><Label htmlFor="email">Email</Label><Input id="email" type="email" required value={f.email} onChange={set("email")} /></div>
            <div className="space-y-2"><Label htmlFor="pw">Password</Label><Input id="pw" type="password" minLength={signup ? 6 : undefined} required value={f.password} onChange={set("password")} /></div>
            {err && <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{err}</p>}
            <Button className="w-full" disabled={busy}>{signup ? "Create account" : "Log in"}</Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {signup ? <>Already have an account? <Link className="text-primary underline" to="/login">Log in</Link></> : <>New here? <Link className="text-primary underline" to="/signup">Create an account</Link></>}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
