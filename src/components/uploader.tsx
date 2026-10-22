"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const ACCEPTED = ["application/pdf", "image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;

type Step = "idle" | "uploading" | "reading" | "checking" | "done" | "error";

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
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  async function handle(file: File) {
    setError(null);
    if (!ACCEPTED.includes(file.type)) return fail("Upload a PDF, PNG, JPG or WEBP file.");
    if (file.size > MAX_BYTES) return fail("Files must be under 10 MB.");
    setFileName(file.name);

    setStep("uploading");
    const supabase = createClient();
    const path = `${folder}/${crypto.randomUUID()}-${file.name.replace(/[^\w.-]/g, "_")}`;
    const { error: uploadError } = await supabase.storage.from("documents").upload(path, file, { contentType: file.type });
    if (uploadError) return fail(uploadError.message);

    setStep("reading");
    // The server action does extraction + checks in one call; flip the label
    // part-way so the user sees both phases.
    const timer = setTimeout(() => setStep("checking"), 4000);
    const result = await process(path, file.type, file.name).catch((e: Error) => ({ error: e.message, id: undefined }));
    clearTimeout(timer);
    if (result.error || !result.id) return fail(result.error ?? "Processing failed.");

    setStep("done");
    router.push(`${detailBase}/${result.id}`);
  }

  function fail(message: string) {
    setError(message);
    setStep("error");
  }

  const busy = step === "uploading" || step === "reading" || step === "checking" || step === "done";
  const steps: { key: Step; label: string }[] = [
    { key: "uploading", label: "Uploading document" },
    { key: "reading", label: "AI reading the document" },
    { key: "checking", label: "Checking against records" },
  ];
  const order: Step[] = ["uploading", "reading", "checking", "done"];

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
        const file = e.dataTransfer.files[0];
        if (file && !busy) handle(file);
      }}
      className={`card border-dashed p-6 transition-colors ${dragging ? "border-brand-500 bg-brand-50" : ""}`}
    >
      {!busy ? (
        <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
          <div className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-600">
            <UploadCloud className="size-6" />
          </div>
          <div className="flex-1">
            <p className="font-medium">{title}</p>
            <p className="text-sm text-muted">{hint}</p>
            {error && (
              <p className="mt-2 flex items-center gap-1.5 text-sm text-red-700">
                <AlertCircle className="size-4" /> {error}
              </p>
            )}
          </div>
          <button className="btn-primary" onClick={() => inputRef.current?.click()}>
            Choose file
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(",")}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handle(file);
              e.target.value = "";
            }}
          />
        </div>
      ) : (
        <div>
          <p className="mb-3 text-sm font-medium">{fileName}</p>
          <ol className="space-y-2">
            {steps.map((s) => {
              const idx = order.indexOf(s.key);
              const current = order.indexOf(step);
              const state = current > idx ? "done" : current === idx ? "active" : "pending";
              return (
                <li key={s.key} className="flex items-center gap-2.5 text-sm">
                  {state === "done" ? (
                    <CheckCircle2 className="size-4 text-brand-600" />
                  ) : state === "active" ? (
                    <Loader2 className="size-4 animate-spin text-brand-600" />
                  ) : (
                    <span className="size-4 rounded-full border border-line" />
                  )}
                  <span className={state === "pending" ? "text-muted" : ""}>{s.label}</span>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
