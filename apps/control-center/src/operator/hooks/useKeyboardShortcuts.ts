import { useState, useEffect, useCallback, useRef } from "react";

interface KeyboardHandlers {
  onPrevStep: () => void;
  onNextStep: () => void;
  onToggleFollow: () => void;
  onTabSwitch: (tab: string) => void;
  onEscape: () => void;
  onTick: () => void;
  onPause: () => void;
  onResume: () => void;
}

export function useKeyboardShortcuts({
  onPrevStep, onNextStep, onToggleFollow,
  onTabSwitch, onEscape, onTick, onPause, onResume,
}: KeyboardHandlers) {
  const handlersRef = useRef({
    onPrevStep, onNextStep, onToggleFollow,
    onTabSwitch, onEscape, onTick, onPause, onResume,
  });

  useEffect(() => {
    handlersRef.current = {
      onPrevStep, onNextStep, onToggleFollow,
      onTabSwitch, onEscape, onTick, onPause, onResume,
    };
  }, [onPrevStep, onNextStep, onToggleFollow, onTabSwitch, onEscape, onTick, onPause, onResume]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const h = handlersRef.current;
      switch (e.key) {
        case "ArrowLeft":  e.preventDefault(); h.onPrevStep(); break;
        case "ArrowRight": e.preventDefault(); h.onNextStep(); break;
        case " ":          e.preventDefault(); h.onToggleFollow(); break;
        case "1":          e.preventDefault(); h.onTabSwitch("summary"); break;
        case "2":          e.preventDefault(); h.onTabSwitch("diagnostics"); break;
        case "3":          e.preventDefault(); h.onTabSwitch("raw"); break;
        case "Escape":     e.preventDefault(); h.onEscape(); break;
        case "F5":         e.preventDefault(); h.onTick(); break;
        case "F6":         e.preventDefault(); h.onPause(); break;
        case "F7":         e.preventDefault(); h.onResume(); break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}
