import { useEffect, useState } from "react";

/**
 * Debounce a rapidly-changing value (free-text filters, threshold sliders).
 * Used so we do not fire a request per keystroke.
 */
export function useDebounced<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [value, delayMs]);

  return debounced;
}
