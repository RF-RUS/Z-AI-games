import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listVisionProfiles,
  listOllamaModels,
  setSessionModel,
  VisionProfile,
  OllamaModel,
} from "../../unoApiClient";

interface Props {
  sessionId: string | null;
  // Current selection as polled from the session (null = service default).
  current: string | null;
  // Called after a successful switch (polling will also pick it up).
  onChanged?: (profileId: string | null) => void;
}

type Option = {
  profileId: string;
  label: string;
  hint: string;
  group: "profiles" | "ollama";
  disabled?: boolean;
  disabledReason?: string;
};

const DEFAULT_LABEL = "Default (service profile)";

function shortProfileId(id: string): string {
  // local/ollama-vlm-7b -> ollama-vlm-7b ; ollama:qwen2.5vl:7b -> qwen2.5vl:7b
  if (id.startsWith("ollama:")) return id.slice(7);
  const parts = id.split("/");
  return parts[parts.length - 1];
}

export default function ModelPicker({ sessionId, current, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [profiles, setProfiles] = useState<VisionProfile[]>([]);
  const [ollama, setOllama] = useState<OllamaModel[]>([]);
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const [p, o] = await Promise.all([listVisionProfiles(), listOllamaModels()]);
    setProfiles(p);
    setOllama(o.models);
    setOllamaReachable(o.reachable);
  }, []);

  useEffect(() => {
    if (!open) return;
    load();
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, load]);

  const options = useMemo<Option[]>(() => {
    const out: Option[] = [
      { profileId: "", label: DEFAULT_LABEL, hint: "env VLM_PROFILE_ID", group: "profiles" },
    ];
    for (const p of profiles) {
      out.push({
        profileId: p.profile_id,
        label: shortProfileId(p.profile_id),
        hint: p.enabled
          ? `${p.model_name ?? p.profile_id}${p.supports_multimodal ? "" : " · text-only"}`
          : "profile disabled on server",
        group: "profiles",
        disabled: !p.enabled,
        disabledReason: "profile disabled on server",
      });
    }
    for (const m of ollama) {
      // Avoid duplicating models already covered by a file profile (same model_name).
      if (profiles.some((p) => p.model_name === m.name)) continue;
      out.push({
        profileId: m.profile_id,
        label: m.name,
        hint: m.vision
          ? `Ollama · ${m.params ?? "?"} · ${m.size_gb}GB${m.vision ? "" : ""}`
          : "Ollama · text-only (no screenshot sent)",
        group: "ollama",
      });
    }
    return out;
  }, [profiles, ollama]);

  const selectedLabel = current ? shortProfileId(current) : DEFAULT_LABEL;

  const pick = async (profileId: string) => {
    if (!sessionId || switching) return;
    setOpen(false);
    setSwitching(true);
    setError(null);
    try {
      await setSessionModel(sessionId, profileId === "" ? null : profileId);
      onChanged?.(profileId === "" ? null : profileId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="model-picker" ref={rootRef}>
      <button
        type="button"
        className="model-picker-btn"
        onClick={() => setOpen((v) => !v)}
        title="Switch this session's VLM (3b / 7b / any Ollama model)"
        disabled={!sessionId}
      >
        <span className="model-picker-icon">🧠</span>
        <span className="model-picker-label">{switching ? "Switching…" : selectedLabel}</span>
        <span className="model-picker-caret">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="model-picker-menu">
          {error && <div className="model-picker-error">{error}</div>}
          {ollamaReachable === false && (
            <div className="model-picker-note">Ollama offline — only file profiles shown.</div>
          )}
          <div className="model-picker-group">Known profiles</div>
          {options.filter((o) => o.group === "profiles").map((o) => (
            <button
              key={o.profileId || "default"}
              type="button"
              className={`model-picker-item ${current === (o.profileId || null) ? "active" : ""} ${o.disabled ? "disabled" : ""}`}
              onClick={() => !o.disabled && pick(o.profileId)}
              title={o.hint}
              disabled={o.disabled || switching}
            >
              <span className="mp-name">{o.label}</span>
              <span className="mp-hint">{o.hint}</span>
            </button>
          ))}
          {ollama.length > 0 && (
            <div className="model-picker-group">Ollama library</div>
          )}
          {options
            .filter((o) => o.group === "ollama")
            .map((o) => (
              <button
                key={o.profileId}
                type="button"
                className={`model-picker-item ${current === o.profileId ? "active" : ""}`}
                onClick={() => pick(o.profileId)}
                title={o.hint}
                disabled={switching}
              >
                <span className="mp-name">{o.label}</span>
                <span className="mp-hint">{o.hint}</span>
              </button>
            ))}
          <div className="model-picker-footer">
            Takes effect on the next cycle · no restart
          </div>
        </div>
      )}
    </div>
  );
}
