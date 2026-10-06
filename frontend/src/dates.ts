const DATE_KEYS = new Set(["date", "from_date", "to_date", "bill_date", "due_date", "as_on"]);

export function formatDate(value: string): string {
  const raw = (value || "").trim();
  if (!raw) return "";
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`;
  const compact = /^(\d{4})(\d{2})(\d{2})$/.exec(raw);
  if (compact) return `${compact[3]}-${compact[2]}-${compact[1]}`;
  const tally = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec(raw);
  if (tally) {
    const months: Record<string, string> = {
      Jan: "01",
      Feb: "02",
      Mar: "03",
      Apr: "04",
      May: "05",
      Jun: "06",
      Jul: "07",
      Aug: "08",
      Sep: "09",
      Oct: "10",
      Nov: "11",
      Dec: "12",
    };
    const month = months[tally[2]];
    if (month) return `${tally[1].padStart(2, "0")}-${month}-${tally[3]}`;
  }
  return raw;
}

export function formatDateCell(column: string, value: string): string {
  if (!DATE_KEYS.has(column) && !column.endsWith("_date")) return value || "";
  return formatDate(value);
}
