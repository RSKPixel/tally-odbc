import { FormEvent, useEffect, useRef, useState } from "react";
import { api, FetchResult } from "../api";

type Line = { kind: string; text: string };

type RequestBody = {
  collections: string[];
  from_date: string;
  to_date: string;
  full_fetch: boolean;
};

const inflight = new Map<string, Promise<{ job_id: string }>>();

type Props = {
  request: RequestBody;
  onClose: () => void;
  onResults: (results: FetchResult[]) => void;
};

export function FetchTerminal({ request, onClose, onResults }: Props) {
  const [lines, setLines] = useState<Line[]>([]);
  const [prompt, setPrompt] = useState(false);
  const [answer, setAnswer] = useState("");
  const [finished, setFinished] = useState(false);
  const jobId = useRef("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = scroller.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [lines, prompt, finished]);

  useEffect(() => {
    const key = JSON.stringify(request);
    let promise = inflight.get(key);
    if (!promise) {
      promise = api.fetchCollections(request);
      inflight.set(key, promise);
    }
    let source: EventSource | null = null;
    let closed = false;

    promise.then((body) => {
        if (closed) return;
        jobId.current = body.job_id;
        source = new EventSource(`/api/tally/jobs/${body.job_id}/events`);
        let stop = false;
        source.onmessage = (event) => {
          if (stop) return;
          let msg: Line;
          try {
            msg = JSON.parse(String(event.data)) as Line;
          } catch {
            return;
          }
          if (msg.kind === "prompt") {
            setPrompt(true);
            const id = jobId.current;
            if (id) {
              api
                .job(id)
                .then((job) => {
                  if (!closed && job.results) onResults(job.results);
                })
                .catch(() => undefined);
            }
            return;
          }
          if (msg.kind === "done" || msg.kind === "error") {
            stop = true;
            setPrompt(false);
            setFinished(true);
            source?.close();
            return;
          }
          setLines((prev) => [...prev, msg]);
        };
        source.onerror = () => {
          if (closed || stop) return;
          stop = true;
          setLines((prev) => [...prev, { kind: "err", text: "Err lost the progress stream" }]);
          source?.close();
        };
      })
      .catch((err: unknown) => {
        setLines([{ kind: "err", text: `Err ${err instanceof Error ? err.message : "Fetch failed"}` }]);
        setFinished(true);
      });

    return () => {
      closed = true;
      source?.close();
      window.setTimeout(() => {
        if (inflight.get(key) === promise) inflight.delete(key);
      }, 200);
    };
  }, [request, onResults]);

  async function confirm(event: FormEvent) {
    event.preventDefault();
    const typed = answer.trim().toLowerCase();
    const yes = typed !== "n" && typed !== "no";
    setAnswer("");
    setPrompt(false);
    setLines((prev) => [...prev, { kind: "info", text: `Do you want to continue? [Y/n] ${yes ? "Y" : "n"}` }]);
    if (!yes) {
      setLines((prev) => [...prev, { kind: "info", text: "Abort." }]);
      setFinished(true);
      return;
    }
    try {
      await api.syncJob(jobId.current);
    } catch (err) {
      setLines((prev) => [...prev, { kind: "err", text: `Err ${err instanceof Error ? err.message : "Sync failed"}` }]);
      setFinished(true);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex h-[min(70vh,640px)] w-full max-w-3xl flex-col overflow-hidden rounded-lg border-2 border-[#300A24] shadow-2xl"
        style={{ background: "#300A24" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 bg-black/30 px-3 py-2">
          <span className="size-3 rounded-full bg-[#EF2929]" />
          <span className="size-3 rounded-full bg-[#FCE94F]" />
          <span className="size-3 rounded-full bg-[#8AE234]" />
          <span className="ml-2 font-mono text-xs text-[#D3D7CF]">tallysync@officehq: ~</span>
          <button type="button" onClick={onClose} className="ml-auto font-mono text-xs text-[#D3D7CF]">
            close
          </button>
        </div>
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-3 font-mono text-[13px] leading-6 text-[#EEEEEC]">
          {lines.map((line, index) => (
            <TerminalLine key={`${index}-${line.text}`} line={line} />
          ))}
          {prompt ? (
            <form autoComplete="off" onSubmit={(event) => void confirm(event)} className="mt-2">
              <span className="text-[#C4A000]">Do you want to continue? [Y/n] </span>
              <input
                autoFocus
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                className="w-16 bg-transparent text-[#EEEEEC] outline-none"
                aria-label="Sync confirmation"
              />
            </form>
          ) : null}
          {!finished ? <span className="ml-0.5 inline-block h-4 w-2 translate-y-0.5 animate-pulse bg-[#EEEEEC]" /> : null}
        </div>
      </div>
    </div>
  );
}

function TerminalLine({ line }: { line: Line }) {
  if (line.kind === "cmd") {
    return (
      <div>
        <span className="text-[#8AE234]">tallysync@officehq</span>
        <span>:</span>
        <span className="text-[#729FCF]">~</span>
        <span># {line.text}</span>
      </div>
    );
  }
  const color =
    line.kind === "err" ? "text-[#EF2929]" : line.kind === "hit" || line.kind === "ok" ? "text-[#8AE234]" : line.kind === "ign" ? "text-[#C4A000]" : "text-[#EEEEEC]";
  return <div className={color}>{line.text}</div>;
}
