"use client";

import { FormEvent, useState } from "react";
import { login, saveToken } from "@/lib/api";

type Props = { onSuccess: (email: string) => void };

export default function LoginPage({ onSuccess }: Props) {
  const [email, setEmail] = useState("admin@receivai.ae");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await login(email, password);
      saveToken(result.access_token);
      onSuccess(result.admin?.email || email);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Login failed. Please check your credentials."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="receivai-login">
      <div className="login-wave login-wave-top" />
      <div className="login-wave login-wave-bottom" />

      <section className="login-intro">
        <div className="login-brand">
          <div className="login-brand-mark">R</div>
          <div>
            <div className="login-brand-name">ReceivAI UAE</div>
            <div className="login-brand-tagline">
              Agentic Finance Operations<br />&amp; Invoice Intelligence
            </div>
          </div>
        </div>

        <div className="login-features">
          <div className="login-feature">
            <span className="login-feature-mark">01</span>
            <div>
              <h2>Automate Invoices</h2>
              <p>Extract, validate and manage invoice records.</p>
            </div>
          </div>
          <div className="login-feature">
            <span className="login-feature-mark feature-blue">02</span>
            <div>
              <h2>Track Receivables</h2>
              <p>Monitor due dates, overdue balances and collections.</p>
            </div>
          </div>
          <div className="login-feature">
            <span className="login-feature-mark feature-violet">03</span>
            <div>
              <h2>AI Finance Assistant</h2>
              <p>Get intelligent insights and cash-flow forecasts.</p>
            </div>
          </div>
        </div>

        <div className="login-trust-line">
          Designed for smarter finance operations in the UAE
        </div>
      </section>

      <section className="login-form-side">
        <form className="login-panel" onSubmit={handleSubmit}>
          <div className="login-panel-kicker">WELCOME TO</div>
          <h1>Receiv<span>AI UAE</span></h1>
          <p className="login-panel-subtitle">Administrator Login</p>

          {error && <div className="login-error" role="alert">{error}</div>}

          <label className="login-label" htmlFor="admin-email">Email address</label>
          <input
            id="admin-email"
            className="login-input"
            type="email"
            autoComplete="username"
            placeholder="Enter your administrator email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <label className="login-label password-label" htmlFor="admin-password">Password</label>
          <div className="login-password-wrap">
            <input
              id="admin-password"
              className="login-input"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              className="password-toggle"
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>

          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? "Signing in..." : "Sign In"}
          </button>

          <div className="login-security">
            <span className="security-dot" />
            Administrator access only <span className="security-separator">·</span> Secure session
          </div>
        </form>
      </section>
    </main>
  );
}
