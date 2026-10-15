"use client";

import { useCallback, useState } from "react";
import { ApiError } from "@/lib/api";

/**
 * The result of an action, shown where the action was taken.
 *
 * A single message area at the top of a long page meant clicking a button at
 * the bottom and seeing nothing happen. Each section owns its own action state
 * and renders this beside its button.
 */
export function Feedback({ error, notice }: { error?: string; notice?: string }) {
  if (!error && !notice) return null;
  return (
    <div className="feedback">
      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert success" role="status">{notice}</div>}
    </div>
  );
}

export type Action = {
  busy: boolean;
  error: string;
  notice: string;
  /** Runs the action. A returned string is shown as the success notice. */
  run: (action: () => Promise<string | void>) => Promise<boolean>;
  clear: () => void;
};

export function useAction(): Action {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const run = useCallback(async (action: () => Promise<string | void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const message = await action();
      if (message) setNotice(message);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const clear = useCallback(() => {
    setError("");
    setNotice("");
  }, []);

  return { busy, error, notice, run, clear };
}
