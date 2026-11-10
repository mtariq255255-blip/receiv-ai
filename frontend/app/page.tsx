
"use client";

import { useCallback, useEffect, useState } from "react";
import Dashboard from "@/components/Dashboard";
import LoginPage from "@/components/LoginPage";
import {
  clearToken,
  getToken,
  getCurrentAdmin,
} from "@/lib/api";

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [adminEmail, setAdminEmail] = useState("");

  const handleLogout = useCallback(() => {
    clearToken();
    setAdminEmail("");
    setAuthenticated(false);
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      handleLogout();
    };

    window.addEventListener(
      "receivai:unauthorized",
      handleUnauthorized
    );

    async function verifySession() {
      const token = getToken();

      if (!token) {
        setCheckingSession(false);
        return;
      }

      try {
        const result = await getCurrentAdmin();

        setAdminEmail(result.admin?.email || "");
        setAuthenticated(true);
      } catch {
        clearToken();
        setAuthenticated(false);
        setAdminEmail("");
      } finally {
        setCheckingSession(false);
      }
    }

    verifySession();

    return () => {
      window.removeEventListener(
        "receivai:unauthorized",
        handleUnauthorized
      );
    };
  }, [handleLogout]);

  function handleLoginSuccess(email: string) {
    setAdminEmail(email);
    setAuthenticated(true);
  }

  if (checkingSession) {
    return (
      <main className="login-screen">
        <div className="login-card text-center">
          <h2>ReceivAI UAE</h2>
          <p className="muted">Checking your secure session...</p>
        </div>
      </main>
    );
  }

  if (!authenticated) {
    return <LoginPage onSuccess={handleLoginSuccess} />;
  }

  return (
    <Dashboard
      adminEmail={adminEmail}
      onLogout={handleLogout}
    />
  );
}
