import type { ReactNode } from "react";

import { cx } from "../lib/cx";

interface FilterBarProps {
  children: ReactNode;
  /** Right-aligned actions such as "Clear filters". */
  actions?: ReactNode;
  /** Short line describing what the active filters mean. */
  description?: ReactNode;
  className?: string;
}

/**
 * Layout wrapper for filter controls. It is a labelled <form> region so screen
 * readers announce it, and it never submits (no navigation on Enter).
 */
export function FilterBar({ children, actions, description, className }: FilterBarProps) {
  return (
    <form
      className={cx("rounded-md border border-slate-200 bg-white p-3", className)}
      role="search"
      aria-label="Filters"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="flex flex-wrap items-end gap-3">{children}</div>
      {(actions || description) && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2">
          {description ? <p className="text-xs text-slate-600">{description}</p> : <span />}
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      )}
    </form>
  );
}

interface FilterFieldProps {
  label: string;
  htmlFor: string;
  children: ReactNode;
  /** Hint shown under the control. */
  hint?: string;
  className?: string;
}

export function FilterField({ label, htmlFor, children, hint, className }: FilterFieldProps) {
  return (
    <div className={cx("flex min-w-[9rem] flex-col gap-1", className)}>
      <label htmlFor={htmlFor} className="text-[0.7rem] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[0.7rem] text-slate-500">{hint}</p> : null}
    </div>
  );
}

const CONTROL_BASE =
  "rounded border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1 disabled:bg-slate-50 disabled:text-slate-400";

export function TextInput({
  id,
  value,
  onChange,
  placeholder,
  type = "text",
  className,
  ...rest
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
  min?: string;
  max?: string;
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className={cx(CONTROL_BASE, className)}
      {...rest}
    />
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  id,
  value,
  onChange,
  options,
  placeholder,
  className,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  /** When set, renders an "any" option with an empty value. */
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className={cx(CONTROL_BASE, "pr-6", className)}
    >
      {placeholder ? <option value="">{placeholder}</option> : null}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/** Small pill toggle group used by the granularity and severity switches. */
export function ToggleGroup<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string }>;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cx("inline-flex rounded-md border border-slate-300 bg-white p-0.5", className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={active}
            className={cx(
              "rounded px-2.5 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600",
              active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function ClearButton({ onClick, label = "Clear filters" }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-1"
    >
      {label}
    </button>
  );
}

/** Active-filter summary chips, so the user can see what is currently applied. */
export function ActiveFilters({
  filters,
  onClear,
  className,
}: {
  filters: Array<{ label: string; value: string }>;
  onClear: (label: string) => void;
  className?: string;
}) {
  if (filters.length === 0) return null;
  return (
    <ul className={cx("flex flex-wrap items-center gap-1.5", className)} aria-label="Active filters">
      {filters.map((filter) => (
        <li key={filter.label}>
          <button
            type="button"
            onClick={() => onClear(filter.label)}
            className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[0.7rem] text-slate-700 hover:border-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            <span className="text-slate-500">{filter.label}:</span>
            <span className="font-medium">{filter.value}</span>
            <span aria-hidden="true" className="text-slate-400">
              ×
            </span>
            <span className="sr-only">Remove filter</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
