import { useState, useRef, useEffect } from "react";
import { ChatMessage } from "./operatorStore";

interface Props {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  disabled: boolean;
  inputRef?: React.RefObject<HTMLInputElement>;
}

export default function ChatPanel({ messages, onSend, disabled, inputRef }: Props) {
  const [input, setInput] = useState("");
  const internalRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const ref = inputRef ?? internalRef;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || disabled) return;
    onSend(text);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <h3>Chat</h3>
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="muted">Type a message to give the agent a hint or instruction.</p>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg chat-${msg.role}`}>
            <span className="chat-role">
              {msg.role === "operator" ? "You" : msg.role === "agent" ? "Agent" : "System"}
            </span>
            <span className="chat-text">{msg.text}</span>
            {msg.status === "error" && <span className="chat-error">!</span>}
          </div>
        ))}
      </div>
      <div className="chat-input">
        <input
          ref={ref}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Start a session to chat..." : "Type a command or hint... (/ to focus)"}
          disabled={disabled}
          title="Type a command or hint. Press / to focus. Try: pause, resume, take over, return to bot"
        />
        <button type="button" onClick={handleSend} disabled={disabled || !input.trim()} title="Send message (Enter)">
          Send
        </button>
      </div>
    </div>
  );
}
