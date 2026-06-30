export interface AdapterBindingSummary {
  adapter_type: string;
  adapter_id?: string | null;
  attached?: boolean;
  profile_id?: string | null;
  healthy?: boolean;
  last_error?: string | null;
}

export interface SessionAttachSummary {
  adapter_bindings?: AdapterBindingSummary[];
  error?: string | null;
}

export function attachedBindings(detail: SessionAttachSummary): AdapterBindingSummary[] {
  return (detail.adapter_bindings ?? []).filter((b) => b.attached !== false);
}

export function assertRequestedAdapterAttached(
  detail: SessionAttachSummary,
  requestedAdapter: string,
  profileId?: string,
): void {
  const bindings = attachedBindings(detail);
  if (requestedAdapter === "web") {
    const web = bindings.find((b) => b.adapter_type === "web");
    if (!web) {
      const mockBound = bindings.some((b) => b.adapter_type === "mock");
      const suffix = mockBound ? " Session has mock adapter only — web attach did not succeed." : "";
      throw new Error((detail.error ?? "Web adapter attach failed — no web binding on session.") + suffix);
    }
    if (profileId && web.profile_id && web.profile_id !== profileId) {
      throw new Error(`Web profile mismatch: expected ${profileId}, got ${web.profile_id}`);
    }
    return;
  }
  if (requestedAdapter === "windows") {
    const win = bindings.find((b) => b.adapter_type === "windows");
    if (!win) {
      throw new Error(detail.error ?? "Windows adapter attach failed — no windows binding on session.");
    }
    return;
  }
  if (requestedAdapter === "mock") {
    const mock = bindings.find((b) => b.adapter_type === "mock");
    if (!mock) {
      throw new Error(detail.error ?? "Mock adapter attach failed.");
    }
  }
}

export function formatAdapterBindingLabel(binding: AdapterBindingSummary): string {
  const id = binding.adapter_id?.slice(0, 8) ?? "—";
  const profile = binding.profile_id ? ` · ${binding.profile_id}` : "";
  const status = binding.attached ? "✓" : "—";
  return `${binding.adapter_type}${profile} ${id} ${status}`;
}
