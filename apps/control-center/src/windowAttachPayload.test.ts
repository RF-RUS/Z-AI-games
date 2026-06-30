import { describe, expect, it } from "vitest";
import { buildWindowsAttachPayload } from "./windowAttachPayload";

describe("buildWindowsAttachPayload", () => {
  it("includes selected handle fields in attach payload", () => {
    const payload = buildWindowsAttachPayload({
      adapter: "windows",
      windowsProfile: "real-uno-desktop",
      selectedWindow: {
        handle: 123456,
        title: "UNO Championship",
        pid: 4242,
        process_name: "Game.exe",
      },
    });

    expect(payload.window_handle).toBe(123456);
    expect(payload.window_title).toBe("UNO Championship");
    expect(payload.window_pid).toBe(4242);
    expect(payload.launch_test_target).toBe(false);
  });

  it("keeps mock launch when no explicit window is selected", () => {
    const payload = buildWindowsAttachPayload({
      adapter: "windows",
      windowsProfile: "local-mock-uno",
      selectedWindow: null,
    });

    expect(payload.launch_test_target).toBe(true);
    expect(payload.window_handle).toBeUndefined();
  });

  it("defaults web attach to scuffed-uno-web profile", () => {
    const payload = buildWindowsAttachPayload({
      adapter: "web",
      windowsProfile: "real-uno-desktop",
      selectedWindow: null,
    });
    expect(payload.profile_id).toBe("scuffed-uno-web");
    expect(payload.adapter_type).toBe("web");
    expect(payload.target_url).toBe("https://scuffeduno.online/");
  });
});
