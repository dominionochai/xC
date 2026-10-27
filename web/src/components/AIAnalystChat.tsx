"use client";

import { useState, type FormEvent } from "react";

export type AIAnalystChatProps = {
  onAsk(question: string): Promise<string>;
};

export default function AIAnalystChat({ onAsk }: AIAnalystChatProps) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || isLoading) return;

    setError(null);
    setAnswer(null);
    setIsLoading(true);
    try {
      const response = await onAsk(submittedQuestion);
      setAnswer(response);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Unable to get an answer. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="ai-analyst-chat" aria-labelledby="ai-analyst-chat-title">
      <h2 id="ai-analyst-chat-title">AI analyst</h2>
      <form onSubmit={submitQuestion}>
        <label htmlFor="ai-analyst-question">Ask a question about this report</label>
        <input
          id="ai-analyst-question"
          name="question"
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          disabled={isLoading}
          required
          aria-describedby={error ? "ai-analyst-error" : undefined}
        />
        <button type="submit" disabled={isLoading || question.trim().length === 0}>
          {isLoading ? "Asking…" : "Ask"}
        </button>
      </form>
      {isLoading && <p role="status" aria-live="polite">Loading answer…</p>}
      {error && <p id="ai-analyst-error" role="alert">{error}</p>}
      {answer !== null && (
        <div className="ai-analyst-answer" aria-live="polite">
          <h3>Answer</h3>
          <p>{answer}</p>
        </div>
      )}
    </section>
  );
}
