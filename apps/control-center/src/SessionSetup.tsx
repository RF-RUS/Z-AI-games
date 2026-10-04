import { useState, useCallback, useEffect } from "react";
import {
  ServiceHealthState, getProfileCompatibility, ProfileCompatibility, CdpTab,
  listVisionProfiles, listOllamaModels, VisionProfile, OllamaModel,
} from "./unoApiClient";
import GameWindowPicker from "./GameWindowPicker";
import BrowserTabPicker from "./BrowserTabPicker";
import { SelectedGameWindow } from "./windowAttachPayload";

interface Props {
  health: Record<number, ServiceHealthState>;
  onStart: (config: {
    adapterType: string;
    profileId: string;
    selectedWindow?: SelectedGameWindow | null;
    selectedTab?: CdpTab | null;
    gameType?: string;
    vlmProfileId?: string | null;
  }) => void;
}

type AttachStage = "idle" | "resolving_window" | "validating_handle" | "attaching_adapter" | "waiting_for_frame" | "starting_session" | "done" | "error";

const STAGE_LABELS: Record<AttachStage, string> = {
  idle: "",
  resolving_window: "Resolving selected window...",
  validating_handle: "Validating window handle...",
  attaching_adapter: "Attaching to selected window...",
  waiting_for_frame: "Waiting for first frame...",
  starting_session: "Starting session...",
  done: "Session started",
  error: "Attach failed",
};

const WEB_PROFILES = [
  { id: "pizz-uno-web", name: "Pizzuno (DOM, browser)" },
  { id: "scuffed-uno-web", name: "Scuffed Uno (canvas)" },
  { id: "real-unoh-web", name: "Pizzuno (legacy DOM)" },
  { id: "local-mock-uno", name: "Local Mock" },
];

const WINDOWS_PROFILES = [
  { id: "real-uno-desktop", name: "UNO Desktop" },
  { id: "local-mock-uno", name: "Mock Test Target" },
];

function isUrlMatchingDomain(url: string, domains: string[]): boolean {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return domains.some((d) => hostname === d || hostname.endsWith("." + d));
  } catch {
    return false;
  }
}

function findMatchingProfiles(
  tabUrl: string,
  compatibilities: Map<string, ProfileCompatibility>
): ProfileCompatibility[] {
  const matches: ProfileCompatibility[] = [];
  for (const compat of compatibilities.values()) {
    if (compat.allowed_domains.length > 0 && isUrlMatchingDomain(tabUrl, compat.allowed_domains)) {
      matches.push(compat);
    }
  }
  return matches;
}

const VLM_LAST_PICK_KEY = "uno.session.vlm_profile_id";

function loadLastVlmPick(): string {
  try {
    return localStorage.getItem(VLM_LAST_PICK_KEY) ?? "";
  } catch {
    return "";
  }
}

function shortModelLabel(id: string): string {
  if (id.startsWith("ollama:")) return id.slice(7);
  const parts = id.split("/");
  return parts[parts.length - 1];
}

export default function SessionSetup({ health, onStart }: Props) {
  const [adapterType, setAdapterType] = useState("windows");
  const [profileId, setProfileId] = useState("real-uno-desktop");
  const [selectedWindow, setSelectedWindow] = useState<SelectedGameWindow | null>(null);
  const [selectedTab, setSelectedTab] = useState<CdpTab | null>(null);
  const [starting, setStarting] = useState(false);
  const [attachStage, setAttachStage] = useState<AttachStage>("idle");
  const [attachError, setAttachError] = useState<string | null>(null);
  const [compatMap, setCompatMap] = useState<Map<string, ProfileCompatibility>>(new Map());
  const [autoSuggestion, setAutoSuggestion] = useState<string | null>(null);
  // Vision model (per-session VLM). Remembered across sessions so the operator
  // doesn't re-pick it every New Session (it defaulted to the service profile
  // before, which made A/B-testing models a pain).
  const [vlmProfileId, setVlmProfileId] = useState<string>(loadLastVlmPick);
  const [vlmProfiles, setVlmProfiles] = useState<VisionProfile[]>([]);
  const [vlmOllama, setVlmOllama] = useState<OllamaModel[]>([]);
  const [vlmLoading, setVlmLoading] = useState(true);

  const orchestratorOnline = (health[8100] ?? "offline") !== "offline";
  const adapterOnline = adapterType === "web"
    ? (health[8104] ?? "offline") !== "offline"
    : (health[8105] ?? "offline") !== "offline";

  const profiles = adapterType === "web" ? WEB_PROFILES : WINDOWS_PROFILES;

  useEffect(() => {
    (async () => {
      try {
        const [p, o] = await Promise.all([listVisionProfiles(), listOllamaModels()]);
        setVlmProfiles(p);
        setVlmOllama(o.models);
      } catch {
        // model-runtime offline — the select degrades to "Default" only
      } finally {
        setVlmLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (adapterType !== "web") return;
    const load = async () => {
      const map = new Map<string, ProfileCompatibility>();
      for (const p of WEB_PROFILES) {
        const compat = await getProfileCompatibility(p.id);
        if (compat) map.set(p.id, compat);
      }
      setCompatMap(map);
    };
    load();
  }, [adapterType]);

  const handleTabSelect = useCallback((tab: CdpTab | null) => {
    setSelectedTab(tab);
    setAutoSuggestion(null);
    if (!tab || adapterType !== "web" || compatMap.size === 0) return;

    const matches = findMatchingProfiles(tab.url, compatMap);
    if (matches.length === 1) {
      const suggested = matches[0];
      if (suggested.profile_id !== profileId) {
        setProfileId(suggested.profile_id);
        setAutoSuggestion(`Auto-selected "${suggested.display_name}" based on tab URL`);
        setTimeout(() => setAutoSuggestion(null), 4000);
      }
    } else if (matches.length > 1) {
      setAutoSuggestion(
        `Multiple profiles match this tab: ${matches.map((m) => m.display_name).join(", ")}. Pick one.`
      );
    }
  }, [adapterType, compatMap, profileId]);

  const handleStart = async () => {
    setStarting(true);
    setAttachStage("resolving_window");
    setAttachError(null);
    try {
      if (adapterType === "web" && selectedTab) {
        const compat = await getProfileCompatibility(profileId);
        if (compat && compat.allowed_domains.length > 0) {
          try {
            const tabUrl = new URL(selectedTab.url);
            const hostname = tabUrl.hostname.toLowerCase();
            const isCompatible = compat.allowed_domains.some(
              (d) => hostname === d || hostname.endsWith("." + d)
            );
            if (!isCompatible) {
              setAttachStage("error");
              setAttachError(
                `Tab domain "${hostname}" is incompatible with profile "${compat.display_name}". ` +
                `Allowed domains: ${compat.allowed_domains.join(", ")}. ` +
                `Either select a compatible tab or change the profile.`
              );
              setStarting(false);
              return;
            }
          } catch {
            // URL parse failed — let backend validate
          }
        }
      }
      await new Promise((r) => setTimeout(r, 300));
      setAttachStage("attaching_adapter");
      // Remember the operator's pick so the next New Session starts with it.
      try {
        if (vlmProfileId) localStorage.setItem(VLM_LAST_PICK_KEY, vlmProfileId);
        else localStorage.removeItem(VLM_LAST_PICK_KEY);
      } catch {
        // storage unavailable — no persistence, session still starts
      }
      await onStart({
        adapterType,
        profileId,
        selectedWindow: adapterType === "windows" ? selectedWindow : null,
        selectedTab: adapterType === "web" ? selectedTab : null,
        vlmProfileId: vlmProfileId || null,
      });
      setAttachStage("done");
    } catch (e) {
      setAttachStage("error");
      const msg = e instanceof Error ? e.message : String(e);
      setAttachError(msg.includes("timed out")
        ? `Attach timed out. The ${adapterType} adapter may be slow to respond. Check that the target window is visible and not minimized.`
        : msg
      );
    } finally {
      setStarting(false);
    }
  };

  const profileDisplayName = (id: string) => profiles.find((p) => p.id === id)?.name || id;
  const currentCompat = adapterType === "web" ? compatMap.get(profileId) : null;

  return (
    <div className="session-setup">
      <h2>New Session</h2>

      {!orchestratorOnline && (
        <div className="setup-warning">
          <p>Backend services are not running.</p>
          <p className="muted">Start the backend first: <code>python -m uvicorn ...</code></p>
        </div>
      )}

      <div className="setup-form">
        <label className="setup-label">
          Game Window
          <select
            value={adapterType}
            onChange={(e) => {
              setAdapterType(e.target.value);
              setProfileId(e.target.value === "web" ? "scuffed-uno-web" : "real-uno-desktop");
              setSelectedWindow(null);
              setSelectedTab(null);
              setAutoSuggestion(null);
            }}
          >
            <option value="windows">Windows Desktop App</option>
            <option value="web">Web Browser</option>
          </select>
        </label>

        <label className="setup-label">
          Profile
          <select
            value={profileId}
            onChange={(e) => {
              setProfileId(e.target.value);
              setAutoSuggestion(null);
            }}
          >
            {profiles.map((p) => {
              const compat = compatMap.get(p.id);
              const hasDomainGuard = compat && compat.allowed_domains.length > 0;
              const label = hasDomainGuard
                ? p.name
                : `${p.name} (no domain guard)`;
              return <option key={p.id} value={p.id}>{label}</option>;
            })}
          </select>
        </label>

        {adapterType === "web" && currentCompat && currentCompat.allowed_domains.length > 0 && (
          <p className="muted" style={{ fontSize: "12px", marginTop: "-4px" }}>
            Compatible domains: {currentCompat.allowed_domains.join(", ")}
          </p>
        )}

        <label className="setup-label">
          🧠 Vision model (VLM)
          <select
            value={vlmProfileId}
            onChange={(e) => setVlmProfileId(e.target.value)}
            disabled={starting || vlmLoading}
          >
            <option value="">Default (service profile)</option>
            {vlmProfiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id} disabled={!p.enabled}>
                {shortModelLabel(p.profile_id)}
                {p.enabled && p.supports_multimodal ? "" : " · text-only"}
              </option>
            ))}
            {vlmOllama
              .filter((m) => !vlmProfiles.some((p) => p.model_name === m.name))
              .map((m) => (
                <option key={m.profile_id} value={m.profile_id}>
                  {m.name} {m.vision ? "" : "· text-only"}
                </option>
              ))}
          </select>
        </label>
        <p className="muted" style={{ fontSize: "11px", marginTop: "-4px" }}>
          {vlmLoading
            ? "Loading models…"
            : "Recognizes the board & cards. Remembered for next session; still switchable live."}
        </p>

        {adapterType === "web" && currentCompat && currentCompat.allowed_domains.length === 0 && (
          <p className="muted" style={{ fontSize: "12px", marginTop: "-4px", color: "var(--text-muted)" }}>
            No domain restriction — any tab can be used with this profile
          </p>
        )}

        {autoSuggestion && (
          <div style={{
            fontSize: "12px",
            padding: "4px 8px",
            borderRadius: "var(--radius)",
            background: "rgba(33, 150, 243, 0.1)",
            color: "var(--text-primary)",
            border: "1px solid rgba(33, 150, 243, 0.3)",
          }}>
            {autoSuggestion}
          </div>
        )}

        {adapterType === "windows" && (
          <GameWindowPicker
            selected={selectedWindow}
            onSelect={setSelectedWindow}
            disabled={starting}
            adapterType={adapterType}
          />
        )}

        {adapterType === "web" && (
          <BrowserTabPicker
            selectedTab={selectedTab}
            onSelect={handleTabSelect}
            disabled={starting}
            profileId={profileId}
          />
        )}

        <button
          type="button"
          className="btn btn-primary btn-large"
          onClick={handleStart}
          disabled={starting || !orchestratorOnline || !adapterOnline}
        >
          {starting ? STAGE_LABELS[attachStage] || "Starting..." : "Start Playing"}
        </button>

        {attachStage !== "idle" && attachStage !== "done" && attachStage !== "error" && (
          <div className="attach-progress">
            <span className="attach-progress-dot" />
            <span className="attach-progress-text">{STAGE_LABELS[attachStage]}</span>
          </div>
        )}

        {attachError && (
          <div className="attach-error">
            <p className="error-text">{attachError}</p>
            <p className="muted">If this persists, try: different profile, different window, or restart backend.</p>
          </div>
        )}

        {!adapterOnline && orchestratorOnline && !starting && (
          <p className="setup-hint">
            {adapterType === "web" ? "Web adapter is offline" : "Windows adapter is offline"}
          </p>
        )}
      </div>
    </div>
  );
}
