import { useEffect } from "react";
import { api, post } from "./api";

// Keep an actively used editor alive without extending an abandoned background tab.
export function useDemoActivity(enabled: boolean, idleMinutes = 30) {
  useEffect(() => {
    if (!enabled) return;
    let lastInput = Date.now();
    let lastPing = Date.now();
    let pending = false;
    const activity = () => {
      lastInput = Date.now();
    };
    window.addEventListener("pointerdown", activity, { passive: true });
    window.addEventListener("keydown", activity);
    window.addEventListener("wheel", activity, { passive: true });
    const timer = window.setInterval(() => {
      const current = Date.now();
      if (!pending && current - lastInput >= idleMinutes * 60_000) {
        pending = true;
        void post("/auth/logout")
          .catch(() => {})
          .finally(() => {
            window.dispatchEvent(new Event("session-expired"));
          });
        return;
      }
      if (
        pending ||
        document.visibilityState !== "visible" ||
        current - lastInput > 90_000 ||
        current - lastPing < 120_000
      )
        return;
      pending = true;
      lastPing = current;
      void api("/auth/me")
        .catch(() => {})
        .finally(() => {
          pending = false;
        });
    }, 60_000);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pointerdown", activity);
      window.removeEventListener("keydown", activity);
      window.removeEventListener("wheel", activity);
    };
  }, [enabled, idleMinutes]);
}
