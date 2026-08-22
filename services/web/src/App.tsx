import { useEffect, useState } from "react";

/**
 * Placeholder app shell. Real screens (Dashboard, My Tasks, Client
 * Workspace, etc.) land per the Sprint Plan starting Sprint 1-2 — this
 * just proves the frontend can reach the FastAPI backend end to end,
 * and gives the next screen a place to be built.
 */
export default function App() {
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    fetch("/api/v1/health")
      .then((res) => (res.ok ? setApiStatus("ok") : setApiStatus("error")))
      .catch(() => setApiStatus("error"));
  }, []);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="rounded-2xl bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-teal">CAOS</h1>
        <p className="mt-1 text-sm text-slate">Practice Automation Platform</p>
        <p className="mt-4 text-xs">
          API status:{" "}
          <span
            className={
              apiStatus === "ok"
                ? "text-green-700"
                : apiStatus === "error"
                  ? "text-coral"
                  : "text-slate"
            }
          >
            {apiStatus}
          </span>
        </p>
      </div>
    </div>
  );
}
