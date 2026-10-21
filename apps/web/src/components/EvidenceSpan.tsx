import { useMemo } from "react";

import { cx } from "../lib/cx";
import { entityStyle, sentimentStyle } from "../lib/format";
import type { EntityPrediction, EntityType, EvidenceSpan as Span, SentimentLabel } from "../lib/schemas";

// ---------------------------------------------------------------------------
// Single span highlight
// ---------------------------------------------------------------------------

interface EvidenceSpanProps {
  span: Span;
  tone?: "sentiment" | "entity" | "neutral";
  entityType?: EntityType | null;
  sentiment?: SentimentLabel | null;
  /** Rendered as a superscript marker, e.g. "1" for citation numbers. */
  marker?: string | number | null;
  className?: string;
  title?: string;
}

/**
 * Highlights a span of source text.
 *
 * IMPORTANT: this renders *supporting text*, not proof of influence. The title
 * attribute says so explicitly, and there is deliberately no attention/heat
 * visualisation anywhere in this app.
 */
export function EvidenceSpan({
  span,
  tone = "neutral",
  entityType,
  sentiment,
  marker,
  className,
  title,
}: EvidenceSpanProps) {
  let background: string | undefined;
  let border: string | undefined;
  let textColour: string | undefined;

  if (tone === "entity" && entityType) {
    const style = entityStyle(entityType);
    background = `${style.hex}1a`;
    border = style.hex;
    textColour = style.hex;
  } else if (tone === "sentiment" && sentiment) {
    const style = sentimentStyle(sentiment);
    background = `${style.hex}1a`;
    border = style.hex;
    textColour = style.hex;
  }

  return (
    <mark
      className={cx(
        "rounded-sm px-0.5 decoration-transparent",
        tone === "neutral" && "bg-slate-100 text-inherit",
        className,
      )}
      style={{
        backgroundColor: background,
        borderBottom: border ? `2px solid ${border}` : undefined,
        color: textColour ?? undefined,
      }}
      title={
        title ??
        "Evidence span: supporting text the model keyed on. Supporting text, not causal attribution."
      }
    >
      {span.text}
      {marker !== null && marker !== undefined ? (
        <sup className="ml-0.5 font-mono text-[0.6rem] text-slate-500">{marker}</sup>
      ) : null}
    </mark>
  );
}

// ---------------------------------------------------------------------------
// Annotated text: renders source text with spans highlighted
// ---------------------------------------------------------------------------

export interface Annotation {
  start: number;
  end: number;
  text: string;
  tone: "sentiment" | "entity" | "neutral";
  entityType?: EntityType | null;
  sentiment?: SentimentLabel | null;
  label?: string;
  marker?: string | number | null;
}

interface AnnotatedTextProps {
  text: string;
  annotations: Annotation[];
  /** Render paragraph breaks as separate blocks. Defaults to true. */
  paragraphs?: boolean;
  className?: string;
  /** Shown above the text. */
  caption?: string;
}

function overlaps(a: Annotation, b: Annotation): boolean {
  return a.start < b.end && b.start < a.end;
}

/**
 * Renders article text with entity and sentiment spans highlighted.
 *
 * Overlapping annotations are resolved by keeping the earlier-starting (and
 * then longer) span, and dropping the rest. We never invent text: any span
 * whose offsets fall outside the string, or whose text does not match the
 * slice, is dropped rather than shifted. Silently relocating offsets would
 * misrepresent which words the model actually saw.
 */
export function AnnotatedText({
  text,
  annotations,
  paragraphs = true,
  className,
  caption,
}: AnnotatedTextProps) {
  const sorted = useMemo(() => {
    const valid = annotations
      .filter((annotation) => {
        if (annotation.start < 0 || annotation.end > text.length) return false;
        if (annotation.end <= annotation.start) return false;
        return text.slice(annotation.start, annotation.end) === annotation.text;
      })
      .sort((a, b) => a.start - b.start || b.end - a.end);

    const kept: Annotation[] = [];
    for (const annotation of valid) {
      if (kept.some((existing) => overlaps(existing, annotation))) continue;
      kept.push(annotation);
    }
    return kept;
  }, [annotations, text]);

  const nodes = useMemo(() => {
    const out: Array<{ kind: "plain" | "span"; value: string; annotation?: Annotation }> = [];
    let cursor = 0;
    for (const annotation of sorted) {
      if (annotation.start > cursor) {
        out.push({ kind: "plain", value: text.slice(cursor, annotation.start) });
      }
      out.push({
        kind: "span",
        value: text.slice(annotation.start, annotation.end),
        annotation,
      });
      cursor = annotation.end;
    }
    if (cursor < text.length) out.push({ kind: "plain", value: text.slice(cursor) });
    return out;
  }, [sorted, text]);

  const blocks = useMemo(() => {
    if (!paragraphs) return [nodes];
    const result: Array<typeof nodes> = [];
    let current: typeof nodes = [];
    for (const node of nodes) {
      if (node.kind === "plain" && node.value.includes("\n\n")) {
        const parts = node.value.split("\n\n");
        parts.forEach((part, index) => {
          if (index > 0) {
            result.push(current);
            current = [];
          }
          if (part) current.push({ kind: "plain", value: part });
        });
      } else {
        current.push(node);
      }
    }
    if (current.length > 0) result.push(current);
    return result;
  }, [nodes, paragraphs]);

  return (
    <div className={cx("space-y-3", className)}>
      {caption ? (
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{caption}</p>
      ) : null}
      <div className="space-y-3 text-sm leading-relaxed text-slate-800">
        {blocks.map((block, blockIndex) => (
          <p key={blockIndex}>
            {block.map((node, nodeIndex) =>
              node.kind === "span" && node.annotation ? (
                <EvidenceSpan
                  key={nodeIndex}
                  span={{
                    text: node.value,
                    start: node.annotation.start,
                    end: node.annotation.end,
                  }}
                  tone={node.annotation.tone}
                  entityType={node.annotation.entityType ?? null}
                  sentiment={node.annotation.sentiment ?? null}
                  marker={node.annotation.marker ?? null}
                  title={node.annotation.label}
                />
              ) : (
                <span key={nodeIndex}>{node.value}</span>
              ),
            )}
          </p>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence span list (used in prediction cards)
// ---------------------------------------------------------------------------

interface EvidenceListProps {
  spans: Span[];
  model?: { name: string; version: string } | null;
  emptyMessage?: string;
  className?: string;
}

/**
 * A plain list of evidence spans. When empty, we say so explicitly — an empty
 * evidence list is meaningful and must not silently disappear.
 */
export function EvidenceList({ spans, model, emptyMessage, className }: EvidenceListProps) {
  if (spans.length === 0) {
    return (
      <p className={cx("rounded border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-600", className)}>
        {emptyMessage ?? "No evidence span returned for this prediction."}
      </p>
    );
  }

  return (
    <ul className={cx("space-y-2", className)}>
      {spans.map((span, index) => (
        <li
          key={`${span.start}-${span.end}-${index}`}
          className="rounded border-l-2 border-slate-300 bg-slate-50 px-3 py-2"
        >
          <blockquote className="text-sm italic text-slate-700">“{span.text}”</blockquote>
          <p className="mt-1 font-mono text-[0.65rem] text-slate-500">
            chars {span.start}–{span.end}
            {model ? ` · ${model.name}@${model.version}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}

/** Convenience: build annotations from entity predictions. */
export function entityAnnotations(entities: EntityPrediction[]): Annotation[] {
  return entities.map((entity) => ({
    start: entity.span.start,
    end: entity.span.end,
    text: entity.span.text,
    tone: "entity" as const,
    entityType: entity.span.entity_type,
    label: `${entity.span.entity_type}${entity.canonical_name ? ` · ${entity.canonical_name}` : ""}${
      entity.resolution_method ? ` · resolved via ${entity.resolution_method}` : ""
    }`,
  }));
}
