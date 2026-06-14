// Display helpers — the browser renders ₹ fine (unlike the Helvetica PDF).

export function inr(x?: number | null): string {
  if (x === null || x === undefined) return "—";
  if (x >= 1e7) return `₹${(x / 1e7).toFixed(2)} Cr`;
  if (x >= 1e5) return `₹${(x / 1e5).toFixed(1)} L`;
  return `₹${Math.round(x).toLocaleString("en-IN")}`;
}

export function pct(x?: number | null, digits = 0): string {
  if (x === null || x === undefined) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

export function titleCase(s?: string | null): string {
  if (!s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}
