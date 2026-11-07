export function toUtcDateTimeLocalValue(value: unknown) {
  const date = parseDateTime(value);
  return date === null ? "" : formatDateTimeLocal(date);
}

export function fromUtcDateTimeLocalValue(value: string) {
  const date = parseLocalDateTime(value);
  return date === null ? "" : formatUtcDateTime(date);
}

export function normalizeUtcDateTimeValue(value: unknown): unknown {
  if (typeof value !== "string" || value.trim().length === 0) {
    return value;
  }

  const localDate = parseLocalDateTime(value);
  if (localDate !== null) {
    return formatUtcDateTime(localDate);
  }

  const date = parseDateTime(value);
  return date === null ? value : formatUtcDateTime(date);
}

export function formatUtcDateTimeForDisplay(value: unknown, locale: string) {
  const date = parseDateTime(value);
  if (date === null) {
    return typeof value === "string" ? value : "";
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

export function formatDateForDisplay(value: unknown, locale: string) {
  const date = parseDate(value);
  if (date === null) {
    return typeof value === "string" ? value : "";
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

function parseDateTime(value: unknown) {
  if (typeof value !== "string" || value.trim().length === 0) {
    return null;
  }

  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(trimmed)) {
    return null;
  }

  const timestamp = Date.parse(trimmed);
  if (Number.isNaN(timestamp)) {
    return null;
  }

  return new Date(timestamp);
}

function parseLocalDateTime(value: string) {
  const match = value.trim().match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/,
  );
  if (match === null) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hours = Number(match[4]);
  const minutes = Number(match[5]);
  const seconds = Number(match[6] ?? "0");
  const milliseconds = Number((match[7] ?? "").padEnd(3, "0") || "0");
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hours, minutes, seconds, milliseconds);

  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
    || date.getUTCHours() !== hours
    || date.getUTCMinutes() !== minutes
    || date.getUTCSeconds() !== seconds
    || date.getUTCMilliseconds() !== milliseconds
  ) {
    return null;
  }

  return date;
}

function parseDate(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }

  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match === null) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(0, 0, 0, 0);

  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) {
    return null;
  }

  return date;
}

function formatDateTimeLocal(date: Date) {
  const year = `${date.getUTCFullYear()}`.padStart(4, "0");
  const month = `${date.getUTCMonth() + 1}`.padStart(2, "0");
  const day = `${date.getUTCDate()}`.padStart(2, "0");
  const hours = `${date.getUTCHours()}`.padStart(2, "0");
  const minutes = `${date.getUTCMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatUtcDateTime(date: Date) {
  const seconds = `${date.getUTCSeconds()}`.padStart(2, "0");
  return `${formatDateTimeLocal(date)}:${seconds}Z`;
}
