import { FileText, ExternalLink } from "lucide-react";

export function DocumentPreview({ url, fileName }: { url: string | null; fileName: string | null }) {
  const isPdf = fileName?.toLowerCase().endsWith(".pdf");
  return (
    <section className="card overflow-hidden lg:sticky lg:top-6">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <FileText className="size-4 shrink-0 text-muted" />
          <span className="truncate">{fileName ?? "Document"}</span>
        </span>
        {url && (
          <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-brand-600 hover:underline">
            Open <ExternalLink className="size-3" />
          </a>
        )}
      </header>
      <div className="bg-stone-100">
        {!url ? (
          <p className="p-10 text-center text-sm text-muted">Original document unavailable.</p>
        ) : isPdf ? (
          <iframe src={url} title="Original document" className="h-[640px] w-full" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt="Original document" className="mx-auto max-h-[640px] w-auto" />
        )}
      </div>
    </section>
  );
}
