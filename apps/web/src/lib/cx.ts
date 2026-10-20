/**
 * Tiny className combiner — a local stand-in for `clsx` + `tailwind-merge`.
 *
 * We only need: conditional classes, arrays, objects, and "later class wins"
 * for a small set of known Tailwind conflict groups. Keeping it local avoids
 * two extra runtime dependencies for ~40 lines of code.
 */

export type ClassValue =
  | string
  | number
  | null
  | false
  | undefined
  | ClassValue[]
  | Record<string, boolean | null | undefined>;

function flatten(value: ClassValue, out: string[]): void {
  if (value === null || value === undefined || value === false || value === "") return;
  if (typeof value === "string") {
    out.push(value);
    return;
  }
  if (typeof value === "number") {
    out.push(String(value));
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) flatten(item, out);
    return;
  }
  if (typeof value === "object") {
    for (const [key, on] of Object.entries(value)) {
      if (on) out.push(key);
    }
  }
}

/**
 * Conflict groups we actually use. Prefix-based groups (rounded, border, p-,
 * etc.) are handled by `prefixConflictKey` below.
 */
const EXACT_CONFLICT_GROUPS: Record<string, string[]> = {};

const PREFIX_CONFLICT_GROUPS: Array<{ test: RegExp; group: string }> = [
  { test: /^m[trblxy]?-/, group: "margin" },
  { test: /^p[trblxy]?-/, group: "padding" },
  { test: /^-?mx-/, group: "margin-x" },
  { test: /^-?my-/, group: "margin-y" },
  { test: /^rounded(-|$)/, group: "radius" },
  { test: /^border(-|$)/, group: "border" },
  { test: /^text-(xs|sm|base|lg|xl|2xl|3xl)$/, group: "font-size" },
  { test: /^font-(thin|normal|medium|semibold|bold)$/, group: "font-weight" },
  { test: /^w-/, group: "width" },
  { test: /^h-/, group: "height" },
  { test: /^bg-/, group: "background" },
  { test: /^(opacity)-/, group: "opacity" },
  { test: /^gap-/, group: "gap" },
  { test: /^items-/, group: "align-items" },
  { test: /^justify-/, group: "justify" },
  { test: /^shadow(-|$)/, group: "shadow" },
  { test: /^ring(-|$)/, group: "ring" },
  { test: /^leading-/, group: "line-height" },
  { test: /^truncate$|^whitespace-/, group: "text-wrap" },
];

function conflictKey(className: string): string | null {
  // Ignore variants (`hover:`, `md:`, …) and arbitrary values for safety: we
  // only dedupe the simple base utilities, which is where conflicts bite.
  if (className.includes(":")) return null;
  if (className.includes("[")) return null;

  const exact = EXACT_CONFLICT_GROUPS[className];
  if (exact) return exact.join("|");

  for (const { test, group } of PREFIX_CONFLICT_GROUPS) {
    if (test.test(className)) return group;
  }
  return null;
}

/**
 * Join class names, dropping falsy values and resolving last-wins conflicts.
 *
 * @example cx("p-2", isActive && "bg-brand-600", ["rounded", { "opacity-50": disabled }])
 */
export function cx(...inputs: ClassValue[]): string {
  const tokens: string[] = [];
  flatten(inputs, tokens);

  const ordered: string[] = [];
  const lastIndexForGroup = new Map<string, number>();

  for (const token of tokens) {
    for (const part of token.split(/\s+/)) {
      if (!part) continue;
      const group = conflictKey(part);
      if (group) {
        // Reserve this group's slot with the newest value.
        const previous = lastIndexForGroup.get(group);
        if (previous !== undefined) ordered[previous] = "";
      }
      ordered.push(part);
      if (group) lastIndexForGroup.set(group, ordered.length - 1);
    }
  }

  return ordered.filter(Boolean).join(" ");
}

export default cx;
