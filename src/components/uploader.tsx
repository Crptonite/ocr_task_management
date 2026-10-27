"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { UploadCloud, Loader2, CheckCircle2, AlertCircle, Clock, X } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const ACCEPTED = ["application/pdf", "image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 100;
const CONCURRENCY = 3; // files processed in parallel; keeps the AI provider's rate limits happy

type Status = "queued" | "uploading" | "reading" | "done" | "error";
type Item = { key: string; file: File; status: Status; id?: string; error?: string };

export function Uploader({
  folder,
  title,
  hint,
  process,
  detailBase,
}: {
  folder: "invoices" | "orders";
  title: string;
  hint: string;
  process: (path: string, mediaType: string, fileName: string) => Promise<{ id?: string; error?: string }>;
  detailBase: string;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const running = items.some((i) => i.status === "queued" || i.status === "uploading" || i.status === "reading");
  const done = items.filter((i) => i.status === "done").length;
  const failed = items.filter((i) => i.status === "error").length;
  const finished = done + failed;

  const update = (key: string, patch: Partial<Item>) =>
    setItems((list) => list.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  async function processOne(item: Item) {
    const { file, key } = item;
    if (!ACCEPTED.includes(file.type)) return update(key, { status: "error", error: "Not a PDF, PNG, JPG or WEBP" });
    if (file.size > MAX_BYTES) return update(key, { status: "error", error: "Larger than 10 MB" });

    update(key, { status: "uploading" });
    const path = `${folder}/${crypto.randomUUID()}-${file.name.replace(/[^\w.-]/g, "_")}`;
    const { error: uploadError } = await createClient()
      .storage.from("documents")
      .upload(path, file, { contentType: file.type });
    if (uploadError) return update(key, { status: "error", error: uploadError.message });

    update(key, { status: "reading" });
    const result = await process(path, file.type, file.name).catch((e: Error) => ({ error: e.message, id: undefined }));
    if (result.error || !result.id) return update(key, { status: "error", error: result.error ?? "Processing failed" });
    update(key, { status: "done", id: result.id });
    return result.id;
  }

  async function handle(fileList: FileList | File[]) {
    setNotice(null);
    let files = Array.from(fileList);
    if (files.length === 0) return;
    if (files.length > MAX_FILES) {
      setNotice(`Only the first ${MAX_FILES} of ${files.length} files were added.`);
      files = files.slice(0, MAX_FILES);
    }
    const batch: Item[] = files.map((file) => ({ key: crypto.randomUUID(), file, status: "queued" }));
    setItems(batch);

    // Simple worker pool: CONCURRENCY workers pull from a shared queue.
    const queue = [...batch];
    const ids: (string | void)[] = [];
    await Promise.all(
      Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
        for (let next = queue.shift(); next; next = queue.shift()) ids.push(await processOne(next));
      }),
    );

    // A single file goes straight to its result, like before.
    if (batch.length === 1 && ids[0]) router.push(`${detailBase}/${ids[0]}`);
    else router.refresh();
  }

  const statusIcon = (s: Status) =>
    s === "done" ? (
      <CheckCircle2 className="size-4 text-brand-600" />
    ) : s === "error" ? (
      <AlertCircle className="size-4 text-red-600" />
    ) : s === "queued" ? (
      <Clock className="size-4 text-muted" />
    ) : (
      <Loader2 className="size-4 animate-spin text-brand-600" />
    );
  const statusLabel: Record<Status, string> = {
    queued: "Waiting",
    uploading: "Uploading",
    reading: "AI reading & checking",
    done: "Done",
    error: "Failed",
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!running) handle(e.dataTransfer.files);
      }}
      className={`card border-dashed p-6 transition-colors ${dragging ? "border-brand-500 bg-brand-50" : ""}`}
    >
      <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
        <div className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-600">
          {running ? <Loader2 className="size-6 animate-spin" /> : <UploadCloud className="size-6" />}
        </div>
        <div className="flex-1">
          <p className="font-medium">{running ? `Processing ${finished} of ${items.length}…` : title}</p>
          <p className="text-sm text-muted">{running ? "You can stay on this page while the batch runs." : hint}</p>
          {notice && <p className="mt-1 text-sm text-amber-700">{notice}</p>}
        </div>
        <button className="btn-primary" disabled={running} onClick={() => inputRef.current?.click()}>
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED.join(",")}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) handle(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {items.length > 1 || (items.length === 1 && items[0].status === "error") ? (
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-xs text-muted">
            <span>
              {done} done · {failed} failed · {items.length - finished} remaining
            </span>
            {!running && (
              <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setItems([])}>
                <X className="size-3.5" /> Clear
              </button>
            )}
          </div>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-canvas">
            <div
              className="h-full rounded-full bg-brand-500 transition-all"
              style={{ width: `${items.length ? (finished / items.length) * 100 : 0}%` }}
            />
          </div>
          <ul className="max-h-72 divide-y divide-line overflow-y-auto rounded-lg border border-line text-sm">
            {items.map((i) => (
              <li key={i.key} className="flex items-center gap-3 px-3 py-2">
                {statusIcon(i.status)}
                <span className="min-w-0 flex-1 truncate">{i.file.name}</span>
                {i.status === "done" && i.id ? (
                  <Link href={`${detailBase}/${i.id}`} className="text-xs text-brand-600 hover:underline">
                    Open result
                  </Link>
                ) : (
                  <span className={`text-xs ${i.status === "error" ? "text-red-700" : "text-muted"}`}>
                    {i.status === "error" ? i.error : statusLabel[i.status]}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
