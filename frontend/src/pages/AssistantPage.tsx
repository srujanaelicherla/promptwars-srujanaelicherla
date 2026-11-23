import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  queryAssistant,
  type AssistantQueryResponse,
  type CitationView,
} from "../utilities/api";
import { buttonClassName, cardClassName, secondaryButtonClassName, textLinkClassName } from "../utilities/classes";
import { usePageTitle } from "../utilities/usePageTitle";

const EXAMPLES = [
  "What is the SYNTHETIC booking duration limit?",
  "What laser eyewear is listed in the synthetic laser safety notes?",
  "How should the fume hood sash be set according to the synthetic usage notes?",
];

type ThreadItem = {
  question: string;
  answer: AssistantQueryResponse | null;
  error: string | null;
};

function citationLabel(item: CitationView): string {
  return `${item.title}, ${item.section}`;
}

export function AssistantPage() {
  usePageTitle("LabLink AI Assistant · LabLink");
  const questionId = useId();
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  function markUnavailable(caught: unknown): void {
    if (caught instanceof ApiError && (caught.status === 503 || caught.code === "unavailable")) {
      setUnavailable(true);
    }
  }

  async function runQuestion(text: string): Promise<void> {
    const trimmed = text.trim();
    if (trimmed.length < 4) {
      return;
    }
    setAsking(true);
    setAskError(null);
    setThread((current) => [...current, { question: trimmed, answer: null, error: null }]);
    try {
      const result = await queryAssistant(trimmed);
      setThread((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last) {
          next[next.length - 1] = { question: last.question, answer: result, error: null };
        }
        return next;
      });
    } catch (caught: unknown) {
      const message = caught instanceof ApiError ? caught.message : "The assistant could not answer.";
      markUnavailable(caught);
      setAskError(message);
      setThread((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        if (last) {
          next[next.length - 1] = { question: last.question, answer: null, error: message };
        }
        return next;
      });
    } finally {
      setAsking(false);
    }
  }

  function onAsk(event: FormEvent): void {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 4) {
      return;
    }
    setQuestion("");
    void runQuestion(trimmed);
  }

  return (
    <AppShell title="LabLink AI Assistant">
      <p className="max-w-2xl leading-7 text-muted">
        Gemini answers questions about the synthetic catalog and bundled manuals, citing its sources.
        The assistant cannot approve requests or create bookings, and it does not invent live
        availability.
      </p>

      {unavailable ? (
        <div className="mt-6">
          <ErrorState
            title="AI unavailable"
            message="Gemini is not configured on the API, or the provider rejected the request. Set GEMINI_API_KEY on the server. No answers are fabricated in the browser."
          />
        </div>
      ) : null}

      <section className={`${cardClassName} mt-8`} aria-labelledby="examples-title">
        <h2 id="examples-title" className="font-display text-xl text-primary">
          Example questions
        </h2>
        <ul className="mt-3 grid list-none gap-2 p-0">
          {EXAMPLES.map((item) => (
            <li key={item}>
              <button
                type="button"
                className={`${secondaryButtonClassName} w-full justify-start text-left`}
                disabled={asking}
                onClick={() => {
                  void runQuestion(item);
                }}
              >
                {item}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <form className={`${cardClassName} mt-6 grid gap-3`} onSubmit={onAsk}>
        <label className="text-sm font-medium text-primary" htmlFor={questionId}>
          Ask the assistant
        </label>
        <textarea
          id={questionId}
          className="min-h-24 w-full rounded-xl border border-line bg-raised px-3 py-2"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
          }}
          disabled={asking}
          maxLength={2000}
        />
        <button className={buttonClassName} type="submit" disabled={asking || question.trim().length < 4}>
          Send question
        </button>
      </form>

      <div className="mt-6" aria-live="polite">
        {asking ? <LoadingState label="Waiting for the assistant" /> : null}
        {askError ? <ErrorState title="Assistant error" message={askError} /> : null}
        {thread.length === 0 ? null : (
          <ol className="grid list-none gap-4 p-0">
            {thread.map((item, index) => (
              <li key={`${item.question}-${index}`} className={cardClassName}>
                <p className="text-sm font-medium text-primary">You</p>
                <p className="mt-1 leading-7">{item.question}</p>
                {item.error ? (
                  <p className="mt-3 text-sm text-muted" role="alert">
                    {item.error}
                  </p>
                ) : item.answer ? (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-primary">Assistant</p>
                    <p className="mt-1 leading-7">{item.answer.answer}</p>
                    {item.answer.evidence_insufficient ? (
                      <p className="mt-2 text-sm text-muted">Retrieved evidence was insufficient.</p>
                    ) : null}
                    {item.answer.refused ? (
                      <p className="mt-2 text-sm text-muted">The assistant refused a booking or policy override.</p>
                    ) : null}
                    {item.answer.citations.length > 0 ? (
                      <ul className="mt-3 list-disc pl-5 text-sm text-muted">
                        {item.answer.citations.map((citation) => (
                          <li key={`${citation.doc_id}-${citation.section}`}>
                            {citationLabel(citation)}
                            {citation.synthetic ? " (synthetic)" : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {item.answer.equipment_ids.length > 0 ? (
                      <ul className="mt-3 flex list-none flex-wrap gap-3 p-0">
                        {item.answer.equipment_ids.map((id) => (
                          <li key={id}>
                            <Link className={textLinkClassName} to={`/equipment/${id}`}>
                              {id}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-muted">Waiting for the API…</p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </AppShell>
  );
}
