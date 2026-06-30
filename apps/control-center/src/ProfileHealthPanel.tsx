import { useEffect, useState } from "react";
import {
  getProfileHealthSummary,
  isAdapterWebOnline,
  ProfileHealthSummary,
} from "./unoApiClient";

const STATUS_CLASS: Record<string, string> = {
  healthy: "health-ok",
  degraded: "health-warn",
  broken: "health-bad",
};

type PanelState =
  | "loading"
  | "mock_unavailable"
  | "adapter_offline"
  | "no_history"
  | "ready"
  | "error";

type Props = {
  profileId?: string;
  adapterMode?: string;
};

export default function ProfileHealthPanel({
  profileId = "real-unoh-web",
  adapterMode = "web",
}: Props) {
  const [summary, setSummary] = useState<ProfileHealthSummary | null>(null);
  const [panelState, setPanelState] = useState<PanelState>("loading");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    if (adapterMode === "mock") {
      setPanelState("mock_unavailable");
      setSummary(null);
      setErrorDetail(null);
      return;
    }

    let cancelled = false;

    const load = async () => {
      setPanelState("loading");
      setErrorDetail(null);
      try {
        const online = await isAdapterWebOnline();
        if (cancelled) return;
        if (!online) {
          setPanelState("adapter_offline");
          setSummary(null);
          return;
        }

        const s = await getProfileHealthSummary(profileId);
        if (cancelled) return;
        setSummary(s);
        if (!s.latest_status && !s.latest_run_id) {
          setPanelState("no_history");
        } else {
          setPanelState("ready");
        }
      } catch (e) {
        if (cancelled) return;
        setSummary(null);
        setPanelState("error");
        setErrorDetail(e instanceof Error ? e.message : String(e));
      }
    };

    load();
    const id = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [profileId, adapterMode]);

  if (panelState === "loading") {
    return (
      <div className="card profile-health">
        <h2>Profile Health</h2>
        <p className="muted">Loading profile health…</p>
      </div>
    );
  }

  if (panelState === "mock_unavailable") {
    return (
      <div className="card profile-health">
        <h2>Profile Health</h2>
        <p className="muted">
          Profile health is unavailable in Mock mode. Selector drift checks apply to the Web
          adapter (<code>real-unoh-web</code> on port 8104), not mock sessions.
        </p>
        <p className="runbook-hint">
          Switch Session Control adapter to <strong>Web (Playwright)</strong> or run{" "}
          <code>python scripts/profile-health-summary.py --profile {profileId}</code>
        </p>
      </div>
    );
  }

  if (panelState === "adapter_offline") {
    return (
      <div className="card profile-health">
        <h2>Profile Health</h2>
        <p className="muted">
          Web adapter is offline (port 8104). Start backend: <code>.\scripts\dev-backend.ps1</code>
        </p>
      </div>
    );
  }

  if (panelState === "no_history") {
    return (
      <div className="card profile-health">
        <h2>Profile Health — {profileId}</h2>
        <p className="muted">No health runs recorded yet.</p>
        <p className="runbook-hint">
          Run: <code>python scripts/nightly-profile-smoke.py --profile {profileId} --allow-network</code>
          {" "}or <code>curl http://127.0.0.1:8104/profiles/{profileId}/selector-health</code>
        </p>
      </div>
    );
  }

  if (panelState === "error") {
    return (
      <div className="card profile-health">
        <h2>Profile Health</h2>
        <p className="error-text">Failed to load profile health{errorDetail ? `: ${errorDetail}` : ""}</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="card profile-health">
        <h2>Profile Health</h2>
        <p className="muted">No data</p>
      </div>
    );
  }

  const badge = summary.latest_status ?? "no runs";
  const cls = STATUS_CLASS[badge] ?? "";

  return (
    <div className="card profile-health">
      <h2>Profile Health — {profileId}</h2>
      <p>
        Status: <span className={`health-badge ${cls}`}>{badge}</span>
        {summary.latest_timestamp_ms ? (
          <span className="muted"> · {new Date(summary.latest_timestamp_ms).toLocaleString()}</span>
        ) : null}
      </p>
      <ul className="health-meta">
        <li>Fallback ratio: {(summary.fallback_usage_ratio * 100).toFixed(0)}%</li>
        <li>Consecutive degraded: {summary.consecutive_degraded}</li>
        {summary.latest_report_path ? (
          <li>
            Artifact: <code>{summary.latest_report_path}</code>
          </li>
        ) : null}
      </ul>
      {Object.keys(summary.selector_drift_counts).length > 0 ? (
        <p className="muted">
          Drifting:{" "}
          {Object.entries(summary.selector_drift_counts)
            .map(([k, v]) => `${k}(${v})`)
            .join(", ")}
        </p>
      ) : null}
      {summary.active_alerts.length > 0 ? (
        <ul className="alert-list">
          {summary.active_alerts.map((a, i) => (
            <li key={i} className={`alert-${a.severity}`}>
              {a.severity}: {a.message}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="runbook-hint">
        Runbook: <code>{summary.runbook_path}</code> ·{" "}
        <code>python scripts/profile-health-summary.py --profile {profileId}</code>
      </p>
    </div>
  );
}
