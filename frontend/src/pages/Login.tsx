import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../lib/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const res = await api.post<{ access_token: string }>(path, { email, password });
      setToken(res.access_token);
      navigate("/");
      window.location.reload();
    } catch (err: any) {
      setError(err.message || "Failed");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <form onSubmit={submit} className="card p-6 w-80 space-y-3">
        <div className="text-center mb-2">
          <div className="font-semibold">AI Infrastructure Agent</div>
          <div className="text-xs text-neutral-500">{mode === "login" ? "Sign in" : "Create the first account (becomes admin)"}</div>
        </div>
        <input className="input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        <input className="input" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} type="password" required minLength={8} />
        {error && <div className="text-xs text-red-600">{error}</div>}
        <button className="btn-primary w-full" type="submit">{mode === "login" ? "Sign in" : "Register"}</button>
        <button type="button" className="text-xs text-neutral-500 underline w-full text-center" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
