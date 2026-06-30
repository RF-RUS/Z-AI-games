export interface SelectedGameWindow {
  handle: number;
  title: string;
  pid: number | null;
  process_name?: string | null;
}

export interface WindowAttachPayloadInput {
  adapter: string;
  windowsProfile: string;
  webProfile?: string;
  selectedWindow: SelectedGameWindow | null;
  windowTitleHint?: string;
  selectedTab?: { url: string; id: string } | null;
}

export function buildWindowsAttachPayload(input: WindowAttachPayloadInput): Record<string, unknown> {
  const { adapter, windowsProfile, webProfile = "scuffed-uno-web", selectedWindow, windowTitleHint, selectedTab } = input;
  if (adapter === "web") {
    const body: Record<string, unknown> = {
      adapter_type: adapter,
      profile_id: webProfile,
    };
    if (selectedTab) {
      body.cdp_url = "http://127.0.0.1:9222";
      body.url = selectedTab.url;
      body.mode = "playwright";
    } else if (webProfile === "scuffed-uno-web") {
      body.target_url = "https://scuffeduno.online/";
    }
    return body;
  }
  if (adapter === "mock") {
    return { adapter_type: adapter };
  }
  const explicitWindow = selectedWindow != null;
  return {
    adapter_type: adapter,
    profile_id: windowsProfile,
    windows_use_pywinauto: true,
    launch_test_target: windowsProfile === "local-mock-uno" && !explicitWindow,
    window_handle: selectedWindow?.handle,
    window_title: selectedWindow?.title ?? (windowTitleHint?.trim() || undefined),
    window_pid: selectedWindow?.pid ?? undefined,
  };
}
