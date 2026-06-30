/** Operator command handler — processes free-text commands from the operator.

Phase C: Enhanced with control workflow awareness:
- Commands now respect control mode transitions
- Assist mode creates pending actions
- Manual mode blocks agent execution
- Return-to-bot triggers resync
*/

import {
  pauseSession,
  resumeSession,
  stopSession,
} from "./unoApiClient";
import { OperatorState, OperatorAction, ControlMode, canTransition, createChatMessage, createEvent, createAlert, createPendingAction } from "./operatorStore";

// Command patterns
const PAUSE_PATTERNS = [
  /^pause$/i,
  /^пауза$/i,
  /^stop\b/i,
  /^останови/i,
  /^wait$/i,
  /^подожди$/i,
];

const RESUME_PATTERNS = [
  /^resume$/i,
  /^continue$/i,
  /^продолжай$/i,
  /^play$/i,
  /^играй$/i,
  /^go$/i,
];

const STOP_PATTERNS = [
  /^stop$/i,
  /^kill$/i,
  /^отмена$/i,
  /^выход$/i,
  /^quit$/i,
];

const TAKE_OVER_PATTERNS = [
  /^take over$/i,
  /^я сам/i,
  /^manual$/i,
  /^ручное/i,
  /^беру управление/i,
];

const RETURN_PATTERNS = [
  /^return$/i,
  /^back$/i,
  /^возвращай/i,
  /^продолжай игру/i,
  /^return to bot$/i,
];

const ASSIST_PATTERNS = [
  /^assist$/i,
  /^помощь$/i,
  /^помогай/i,
  /^assisted$/i,
];

const CONFIRM_PATTERNS = [
  /^yes$/i,
  /^да$/i,
  /^ok$/i,
  /^подтверждаю/i,
  /^confirm$/i,
  /^выполняй/i,
  /^approve$/i,
  /^одобряю/i,
];

const DENY_PATTERNS = [
  /^no$/i,
  /^нет$/i,
  /^отмена$/i,
  /^cancel$/i,
  /^не делай/i,
  /^deny$/i,
  /^отклоняю/i,
];

function matchesAny(text: string, patterns: RegExp[]): boolean {
  return patterns.some((p) => p.test(text.trim()));
}

export type CommandResult = {
  acknowledged: boolean;
  action?: string;
  message: string;
};

export function parseCommand(text: string): { type: string; raw: string } {
  const trimmed = text.trim();

  if (matchesAny(trimmed, PAUSE_PATTERNS)) return { type: "pause", raw: trimmed };
  if (matchesAny(trimmed, RESUME_PATTERNS)) return { type: "resume", raw: trimmed };
  if (matchesAny(trimmed, STOP_PATTERNS)) return { type: "stop", raw: trimmed };
  if (matchesAny(trimmed, TAKE_OVER_PATTERNS)) return { type: "take_over", raw: trimmed };
  if (matchesAny(trimmed, RETURN_PATTERNS)) return { type: "return_to_bot", raw: trimmed };
  if (matchesAny(trimmed, ASSIST_PATTERNS)) return { type: "assist", raw: trimmed };
  if (matchesAny(trimmed, CONFIRM_PATTERNS)) return { type: "confirm", raw: trimmed };
  if (matchesAny(trimmed, DENY_PATTERNS)) return { type: "deny", raw: trimmed };

  return { type: "hint", raw: trimmed };
}

export async function executeCommand(
  command: { type: string; raw: string },
  state: OperatorState,
  dispatch: React.Dispatch<OperatorAction>,
): Promise<CommandResult> {
  const { sessionId, controlMode } = state;

  switch (command.type) {
    case "pause":
      if (sessionId) {
        await pauseSession(sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "paused", reason: "Operator paused via command" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Session paused by operator") });
        return { acknowledged: true, action: "pause", message: "Session paused." };
      }
      return { acknowledged: false, message: "No active session to pause." };

    case "resume":
      if (sessionId && canTransition(controlMode, "auto")) {
        await resumeSession(sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "auto", reason: "Operator resumed via command" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Session resumed by operator") });
        return { acknowledged: true, action: "resume", message: "Session resumed. Bot is playing." };
      }
      if (!sessionId) return { acknowledged: false, message: "No active session to resume." };
      return { acknowledged: false, message: `Cannot resume from ${controlMode} mode.` };

    case "stop":
      if (sessionId) {
        await stopSession(sessionId);
        dispatch({ type: "TRANSITION_CONTROL", to: "paused", reason: "Operator stopped" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Session stopped by operator") });
        return { acknowledged: true, action: "stop", message: "Session stopped." };
      }
      return { acknowledged: false, message: "No active session to stop." };

    case "take_over":
      if (canTransition(controlMode, "manual")) {
        dispatch({ type: "TRANSITION_CONTROL", to: "manual", reason: "Operator took manual control" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Operator took manual control") });
        return { acknowledged: true, action: "take_over", message: "Manual control activated. Bot is observing." };
      }
      return { acknowledged: false, message: `Cannot take over from ${controlMode} mode.` };

    case "return_to_bot":
      if (canTransition(controlMode, "returning_to_bot")) {
        dispatch({ type: "TRANSITION_CONTROL", to: "returning_to_bot", reason: "Returning control to bot" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Returning control to bot") });
        // Simulate resync
        await new Promise((r) => setTimeout(r, 500));
        dispatch({ type: "TRANSITION_CONTROL", to: "auto", reason: "Resync complete" });
        return { acknowledged: true, action: "return_to_bot", message: "Bot has resumed autonomous control." };
      }
      return { acknowledged: false, message: `Cannot return to bot from ${controlMode} mode.` };

    case "assist":
      if (canTransition(controlMode, "assist")) {
        dispatch({ type: "TRANSITION_CONTROL", to: "assist", reason: "Switched to assist mode" });
        dispatch({ type: "ADD_EVENT", event: createEvent("command", "Switched to assist mode") });
        return { acknowledged: true, action: "assist", message: "Assist mode activated. Bot will propose actions for approval." };
      }
      return { acknowledged: false, message: `Cannot switch to assist from ${controlMode} mode.` };

    case "confirm":
      return { acknowledged: true, action: "confirm", message: "Confirmed." };

    case "deny":
      return { acknowledged: true, action: "deny", message: "Action denied." };

    case "hint":
      return {
        acknowledged: true,
        action: "hint",
        message: `Hint received: "${command.raw}". The agent will consider this in its next decision.`,
      };

    default:
      return { acknowledged: false, message: `Unknown command: "${command.raw}"` };
  }
}
