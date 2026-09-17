"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, Membership, api } from "@/lib/api";

type SessionState = {
  membership: Membership | null;
  loading: boolean;
  refresh: () => Promise<Membership | null>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [membership, setMembership] = useState<Membership | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<Membership>("/v1/staff/me");
      setMembership(me);
      return me;
    } catch (error) {
      // A 403 here means authenticated but not yet cleared for this role --
      // usually a pending second factor. Either way there is no usable
      // membership to show.
      if (!(error instanceof ApiError)) throw error;
      setMembership(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signOut = useCallback(async () => {
    await api.post("/v1/staff/logout");
    setMembership(null);
    window.location.href = "/login";
  }, []);

  return (
    <SessionContext.Provider value={{ membership, loading, refresh, signOut }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
