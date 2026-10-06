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

  const tabClass = (id: Tab) =>
    `px-4 py-2.5 text-sm ${
      tab === id ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-100"
    }`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="records-title"
        className="flex max-h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
          <h2 id="records-title" className="text-sm font-medium text-white">
            {result.label} · {result.count}
          </h2>
          <button type="button" className="text-sm text-zinc-400 hover:text-zinc-100" onClick={onClose}>
            Close
          </button>
        </div>
        <div role="tablist" className="flex border-b border-zinc-800">
          <button type="button" role="tab" aria-selected={tab === "vouchers"} className={tabClass("vouchers")} onClick={() => setTab("vouchers")}>
            Vouchers
          </button>
          <button type="button" role="tab" aria-selected={tab === "items"} className={tabClass("items")} onClick={() => setTab("items")}>
            Items
          </button>
        </div>
        <div className="overflow-auto">
          {tab === "vouchers" ? (
            result.rows.length === 0 ? (
              <p className="p-6 text-sm text-zinc-500">No records</p>
            ) : (
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-zinc-900">
                  <tr>
                    {result.columns.map((column) => (
                      <th key={column} className="whitespace-nowrap px-3 py-2 font-medium capitalize text-zinc-400">
                        {heading(column)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, index) => (
                    <tr
                      key={row.master_id || String(index)}
                      className={`cursor-pointer border-t border-zinc-800 hover:bg-zinc-900 ${
                        selected === row.master_id ? "bg-zinc-900" : ""
                      }`}
                      onClick={() => void openItems(row.master_id)}
                    >
                      {result.columns.map((column) => (
                        <td key={column} className="whitespace-nowrap px-3 py-2 text-zinc-200">
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
              {busy ? <p className="p-6 text-sm text-zinc-500">Loading items…</p> : null}
              {error ? <p className="p-6 text-sm text-red-400">{error}</p> : null}
              {!busy && !error && !items ? (
                <p className="p-6 text-sm text-zinc-500">Click a voucher to load its items</p>
              ) : null}
              {items && !busy && !error ? (
                items.items.length === 0 ? (
                  <p className="p-6 text-sm text-zinc-500">No items</p>
                ) : (
                  <table className="min-w-full text-left text-sm">
                    <thead className="sticky top-0 bg-zinc-900">
                      <tr>
                        {items.columns.map((column) => (
                          <th key={column} className="whitespace-nowrap px-3 py-2 font-medium capitalize text-zinc-400">
                            {heading(column)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.items.map((row, index) => (
                        <tr key={`${row.master_id}-${row.stock_item}-${index}`} className="border-t border-zinc-800">
                          {items.columns.map((column) => (
                            <td key={column} className="whitespace-nowrap px-3 py-2 text-zinc-200">
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
