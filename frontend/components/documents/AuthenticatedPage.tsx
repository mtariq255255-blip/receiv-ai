"use client";

import { ReactNode, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getCurrentAdmin, getToken } from "@/lib/api";

export default function AuthenticatedPage({
  children,
}: {
  children: ReactNode;
}) {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    if (!getToken()) {
      router.replace("/");
      return () => {
        active = false;
      };
    }

    void getCurrentAdmin()
      .then(() => {
        if (active) setAuthorized(true);
      })
      .catch(() => {
        if (active) router.replace("/");
      })
      .finally(() => {
        if (active) setChecking(false);
      });

    return () => {
      active = false;
    };
  }, [router]);

  if (checking || !authorized) {
    return (
      <main className="document-auth-loading">
        <span className="spinner-border spinner-border-sm me-2" />
        Checking administrator session…
      </main>
    );
  }
  return children;
}
