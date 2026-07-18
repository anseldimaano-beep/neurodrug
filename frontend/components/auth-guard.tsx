"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";

// Routes that must stay reachable without a token.
const PUBLIC_PATHS = ["/login"];

type Status = "checking" | "authed" | "guest";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [status, setStatus] = useState<Status>("checking");
  const [email, setEmail] = useState<string | null>(null);

  const isPublicPath = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("token") : null;

      if (!token) {
        if (!cancelled) setStatus("guest");
        if (!isPublicPath) router.replace("/login");
        return;
      }

      try {
        // Also doubles as token validation — a stale/expired token 401s here.
        const me: any = await api.me();
        if (cancelled) return;
        setEmail(me?.email ?? null);
        setStatus("authed");
        if (isPublicPath) router.replace("/");
      } catch {
        localStorage.removeItem("token");
        if (cancelled) return;
        setStatus("guest");
        if (!isPublicPath) router.replace("/login");
      }
    }

    check();
    return () => {
      cancelled = true;
    };
    // Re-check whenever the route changes (e.g. after logging in / out).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    setStatus("guest");
    router.replace("/login");
  };

  // Never gate the login page itself — that would create a redirect loop.
  if (isPublicPath) {
    return <>{children}</>;
  }

  if (status === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Checking session…
      </div>
    );
  }

  if (status === "guest") {
    // Redirect to /login is already underway; render nothing so protected
    // content never flashes on screen first.
    return null;
  }

  return (
    <>
      <div className="flex justify-end items-center gap-3 px-6 py-2 border-b bg-muted/40 text-sm">
        <span className="text-muted-foreground">
          Signed in as <span className="font-medium text-foreground">{email}</span>
        </span>
        <button
          onClick={handleLogout}
          className="px-3 py-1 rounded border text-sm hover:bg-muted transition-colors"
        >
          Logout
        </button>
      </div>
      {children}
    </>
  );
}
