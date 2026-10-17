import { useEffect, useState } from "react";
import { api, FetchResult, VoucherItems } from "../api";
import { formatDateCell } from "../dates";

type Tab = "vouchers" | "items";
type Props = {
  result: FetchResult;
  onClose: () => void;
};

function heading(key: string) {
  if (key === "itemno") return "item no";
  return key.replaceAll("_", " ");
}

const thBase =
  "sticky top-0 z-10 whitespace-nowrap border-b border-zinc-800 bg-zinc-950 px-3 py-2.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 first:pl-8 last:pr-8";
const tdBase = "whitespace-nowrap border-b border-zinc-800/70 px-3 py-2 text-zinc-200 first:pl-8 last:pr-8";

export function RecordsModal({ result, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("vouchers");
  const [selected, setSelected] = useState("");
  const [items, setItems] = useState<VoucherItems | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  async function openItems(masterId: string) {
    if (!masterId) return;
    setSelected(masterId);
    setTab("items");
    setBusy(true);
    setError("");
    try {
      const body = await api.voucherItems(result.id, masterId);
      setItems(body);
      setError(body.error || "");
    } catch (err) {
      setItems(null);
      setError(err instanceof Error ? err.message : "Could not load items");
    } finally {
      setBusy(false);
    }
  }

  if (
    result.id === "stocksummary" ||
    result.id === "inventory" ||
    result.id === "accounts" ||
    result.id === "costcentres" ||
    result.id === "receivables" ||
    result.id === "payables" ||
    result.id === "daybook"
  ) {
    const numeric = new Set([
      "amount",
      "closing",
      "overdue_days",
      "ledger_amount",
      "costcentre_amt",
      "denominator",
      "packing",
      "conversion",
      "opening_alt",
      "opening_rate",
      "opening_value",
      "inwards_alt",
      "inward_rate",
      "inward_value",
      "outwards_alt",
      "outward_rate",
      "outward_value",
      "closing_alt",
      "closing_rate",
      "closing_value",
    ]);
    return (
      <div className="fixed inset-0 z-50 overflow-hidden bg-black/70" onClick={onClose}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="records-title"
          className="flex h-full max-h-full w-full flex-col overflow-hidden bg-zinc-950"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex shrink-0 items-center justify-between border-b border-zinc-800 px-8 py-3">
            <h2 id="records-title" className="text-sm font-medium text-white">
              {result.label} · {result.count}
            </h2>
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
              Close
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {result.rows.length === 0 ? (
              <p className="px-8 py-6 text-sm text-zinc-500">No records</p>
            ) : (
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr>
                    {result.columns.map((column) => (
                      <th
                        key={column}
                        className={`${thBase} ${numeric.has(column) ? "text-right" : ""}`}
                      >
                        {heading(column)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr
                      key={`${row.master_id || row.voucher_no || row.invoice_no || row.ledger_name || row.cost_centre || row.stock_item}-${index}`}
                      className="hover:bg-zinc-900/60"
                    >
                      {result.columns.map((column) => (
                        <td
                          key={column}
                          className={`${tdBase} ${
                            numeric.has(column) ? "text-right font-mono tabular-nums text-zinc-300" : ""
                          }`}
                        >
                          {formatDateCell(column, row[column] || "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (result.id === "pnl") {
    const months: { key: string; from: string; to: string; lines: Record<string, string>[] }[] = [];
    for (const row of result.rows) {
      const key = `${row.period_from}|${row.period_to}`;
      let month = months.find((item) => item.key === key);
      if (!month) {
        month = { key, from: row.period_from || "", to: row.period_to || "", lines: [] };
        months.push(month);
      }
      month.lines.push(row);
    }
    return (
      <div className="fixed inset-0 z-50 overflow-hidden bg-black/70" onClick={onClose}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="records-title"
          className="flex h-full max-h-full w-full flex-col overflow-hidden bg-zinc-950"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex shrink-0 items-center justify-between border-b border-zinc-800 px-8 py-3">
            <h2 id="records-title" className="text-sm font-medium text-white">
              {result.label} · {result.count}
            </h2>
            <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
              Close
            </button>
          </div>
          {months.length === 0 ? (
            <p className="px-8 py-6 text-sm text-zinc-500">No records</p>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-2 content-start gap-4 overflow-auto px-8 py-6">
              {months.map((month) => (
                <section
                  key={month.key}
                  className={`min-h-0 overflow-auto rounded-xl border border-zinc-800 p-3 ${months.length === 1 ? "col-span-2" : ""}`}
                >
                  <h3 className="font-mono text-xs text-zinc-400">
                    {formatDateCell("period_from", month.from)} – {formatDateCell("period_to", month.to)}
                  </h3>
                  <ul className={`mt-2 ${months.length === 1 ? "grid grid-cols-2 gap-x-8" : ""}`}>
                    {month.lines.map((line, index) => (
                      <li
                        key={`${month.key}-${line.line_no}-${index}`}
                        className="flex items-baseline justify-between gap-3 border-t border-zinc-800 py-1.5 text-sm"
                      >
                        <span className="text-zinc-300">{line.account}</span>
                        <span className="font-mono text-zinc-100">{line.amount}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  const tabClass = (id: Tab) =>
    `px-4 py-2.5 text-sm ${
      tab === id ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-100"
    }`;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/70" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="records-title"
        className="flex h-full max-h-full w-full flex-col overflow-hidden bg-zinc-950"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-zinc-800 px-8 py-3">
          <h2 id="records-title" className="text-sm font-medium text-white">
            {result.label} · {result.count}
          </h2>
          <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            Close
          </button>
        </div>
        <div role="tablist" className="flex shrink-0 border-b border-zinc-800 px-8">
          <button type="button" role="tab" aria-selected={tab === "vouchers"} className={tabClass("vouchers")} onClick={() => setTab("vouchers")}>
            Vouchers
          </button>
          <button type="button" role="tab" aria-selected={tab === "items"} className={tabClass("items")} onClick={() => setTab("items")}>
            Items
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {tab === "vouchers" ? (
            result.rows.length === 0 ? (
              <p className="px-8 py-6 text-sm text-zinc-500">No records</p>
            ) : (
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr>
                    {result.columns.map((column) => (
                      <th key={column} className={thBase}>
                        {heading(column)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr
                      key={row.master_id || String(index)}
                      className={`cursor-pointer hover:bg-zinc-900/60 ${
                        selected === row.master_id ? "bg-zinc-900/80" : ""
                      }`}
                      onClick={() => void openItems(row.master_id)}
                    >
                      {result.columns.map((column) => (
                        <td key={column} className={tdBase}>
                          {formatDateCell(column, row[column] || "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <div>
              {busy ? <p className="px-8 py-6 text-sm text-zinc-500">Loading items…</p> : null}
              {error ? <p className="px-8 py-6 text-sm text-red-400">{error}</p> : null}
              {!busy && !error && !items ? (
                <p className="px-8 py-6 text-sm text-zinc-500">Click a voucher to load its items</p>
              ) : null}
              {items && !busy && !error ? (
                items.items.length === 0 ? (
                  <p className="px-8 py-6 text-sm text-zinc-500">No items</p>
                ) : (
                  <table className="w-full border-collapse text-left text-sm">
                    <thead>
                      <tr>
                        {items.columns.map((column) => (
                          <th
                            key={column}
                            className={`${thBase} ${
                              column === "qty_alt" || column === "conversion" ? "text-right" : ""
                            }`}
                          >
                            {heading(column)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.items.map((row, index) => (
                        <tr
                          key={`${row.master_id}-${row.stock_item}-${index}`}
                          className="hover:bg-zinc-900/60"
                        >
                          {items.columns.map((column) => (
                            <td
                              key={column}
                              className={`${tdBase} ${
                                column === "qty_alt" || column === "conversion"
                                  ? "text-right font-mono tabular-nums text-zinc-300"
                                  : ""
                              }`}
                            >
                              {formatDateCell(column, row[column] || "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
