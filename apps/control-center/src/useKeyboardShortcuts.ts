/** Keyboard shortcuts for the operator client.

Provides global keyboard shortcuts for common operator actions.
Shortcuts are discoverable via tooltips and help text.

Rules:
- No destructive shortcuts without confirmation
- Don't conflict with Windows/Electron/common shortcuts
- All shortcuts are discoverable via tooltips
*/

import { useEffect } from "react";
import { ControlMode, canTransition } from "./operatorStore";

interface ShortcutHandlers {
  onToggleMode: () => void;
  onPause: () => void;
  onResume: () => void;
  onTick: () => void;
  onReturnToBot: () => void;
  onDismissAlert: () => void;
  focusChatInput: () => void;
  controlMode: ControlMode;
  isRunning: boolean;
  isPaused: boolean;
}

const SHORTCUTS = [
  { key: "F5", label: "Start / Tick", ctrl: false },
  { key: "F6", label: "Pause", ctrl: false },
  { key: "F7", label: "Resume", ctrl: false },
  { key: "F8", label: "Toggle Auto/Manual", ctrl: false },
  { key: "F9", label: "Return to Bot", ctrl: false },
  { key: "Escape", label: "Dismiss alert / Focus chat", ctrl: false },
  { key: "/", label: "Focus chat input", ctrl: false },
];

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't capture shortcuts when typing in input fields
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        // Allow Escape to blur input
        if (e.key === "Escape") {
          target.blur();
          e.preventDefault();
        }
        return;
      }

      switch (e.key) {
        case "F5":
          e.preventDefault();
          if (handlers.isPaused) {
            handlers.onResume();
          } else {
            handlers.onTick();
          }
          break;

        case "F6":
          e.preventDefault();
          if (handlers.isRunning) {
            handlers.onPause();
          }
          break;

        case "F7":
          e.preventDefault();
          if (handlers.isPaused) {
            handlers.onResume();
          }
          break;

        case "F8":
          e.preventDefault();
          handlers.onToggleMode();
          break;

        case "F9":
          e.preventDefault();
          if (canTransition(handlers.controlMode, "returning_to_bot")) {
            handlers.onReturnToBot();
          }
          break;

        case "Escape":
          e.preventDefault();
          handlers.onDismissAlert();
          handlers.focusChatInput();
          break;

        case "/":
          e.preventDefault();
          handlers.focusChatInput();
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handlers]);
}

export { SHORTCUTS };
