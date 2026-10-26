import { useState } from "react";

import { ModelBadge } from "../../components/ModelBadge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "../../components/states";

import { useCopilot } from "../../hooks/useCopilot";
import { COPILOT_FRAMING_NOTE } from "../../lib/constants";
import { truncate } from "../../lib/format";

/** Copilot: grounded Q&A with citations, abstaining when evidence is thin. */
export function CopilotPage() {
  const [question, setQuestion] = useState("");
  const copilot = useCopilot();

  return (
    <div className="space-y-6">
      <SectionHeader
        as="h1"
        eyebrow="Copilot"
        title="Ask the corpus"
        subtitle={COPILOT_FRAMING_NOTE}
      />

      <section className="nfs-card">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!question.trim()) return;
            copilot.mutate({ question: question.trim(), top_k: 6 });
          }}
        >
          <label htmlFor="copilot-question" className="block text-sm font-medium text-slate-800">
            Your question
          </label>
          <textarea
            id="copilot-question"
            className="min-h-24 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="[mock] What did coverage say about the latest CBN policy decision?"
            required
          />
          <button
            type="submit"
            disabled={copilot.isPending}
            className="rounded bg-brand-800 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-60"
          >
            {copilot.isPending ? "Retrieving…" : "Ask"}
          </button>
        </form>
      </section>

      <section aria-live="polite">
        {copilot.isPending ? (
          <LoadingSkeleton variant="cards" label="Retrieving evidence and generating an answer" />
        ) : copilot.isError ? (
          <ErrorState error={copilot.error} context="the copilot" onRetry={() => void copilot.reset()} />
        ) : copilot.data ? (
          <div className="nfs-card space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-900">Answer</p>
              <ModelBadge model={copilot.data.model} />
            </div>

            {copilot.data.abstained ? (
              <EmptyState
                title="Abstained"
                description="The copilot declined because indexed evidence did not support a grounded answer. It will not invent one."
              />
            ) : (
              <p className="whitespace-pre-line text-sm text-slate-800">{copilot.data.answer}</p>
            )}

            <div>
              <p className="text-sm font-semibold text-slate-900">Citations</p>
              <ul className="mt-2 space-y-2">
                {copilot.data.citations.map((citation) => (
                  <li key={`${citation.article_id}-${citation.score}`} className="rounded border border-slate-200 bg-white p-3 text-sm">
                    <a
                      href={citation.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-brand-800 underline-offset-2 hover:underline"
                    >
                      {truncate(citation.quote, 180)}
                    </a>
                    <p className="mt-1 text-xs text-slate-500">retrieval score {citation.score.toFixed(3)}</p>
                  </li>
                ))}
              </ul>
            </div>

            <ul className="list-disc pl-5 text-xs text-slate-600">
              {copilot.data.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </div>
        ) : (
          <EmptyState
            title="No answer yet"
            description="Ask a question to see grounded retrieval, citations, and an explicit abstention when evidence is thin."
          />
        )}
      </section>
    </div>
  );
}
