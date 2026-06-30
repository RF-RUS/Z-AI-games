import { describe, expect, it } from "vitest";
import {
  assertRequestedAdapterAttached,
  attachedBindings,
  formatAdapterBindingLabel,
} from "./sessionAdapterAttach";

describe("sessionAdapterAttach", () => {
  it("passes when web binding is attached", () => {
    expect(() =>
      assertRequestedAdapterAttached(
        {
          adapter_bindings: [
            { adapter_type: "web", adapter_id: "abc", attached: true, profile_id: "scuffed-uno-web" },
          ],
        },
        "web",
        "scuffed-uno-web",
      ),
    ).not.toThrow();
  });

  it("fails when only mock is bound for web request", () => {
    expect(() =>
      assertRequestedAdapterAttached(
        {
          adapter_bindings: [{ adapter_type: "mock", adapter_id: "m1", attached: true }],
          error: "web attach failed",
        },
        "web",
        "scuffed-uno-web",
      ),
    ).toThrow(/mock adapter only/);
  });

  it("lists only attached bindings", () => {
    const attached = attachedBindings({
      adapter_bindings: [
        { adapter_type: "web", attached: true },
        { adapter_type: "mock", attached: false },
      ],
    });
    expect(attached).toHaveLength(1);
    expect(attached[0].adapter_type).toBe("web");
  });

  it("formats adapter label with profile", () => {
    const label = formatAdapterBindingLabel({
      adapter_type: "web",
      adapter_id: "12345678-abcd",
      profile_id: "scuffed-uno-web",
      attached: true,
    });
    expect(label).toContain("scuffed-uno-web");
    expect(label).toContain("12345678");
  });
});
