export function money(value: number | string | null | undefined, currency = "SGD") {
  if (value == null || value === "") return "—";
  return new Intl.NumberFormat("en-SG", { style: "currency", currency }).format(Number(value));
}

export function date(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export function dateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(
    new Date(value),
  );
}

export function isOverdue(due: string | null | undefined, status?: string) {
  if (!due || status === "done") return false;
  return due < new Date().toISOString().slice(0, 10);
}

export function initials(name: string | null | undefined) {
  if (!name) return "?";
  return name
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}
