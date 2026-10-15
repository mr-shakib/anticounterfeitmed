"use client";

import { useEffect, useState } from "react";
import { Feedback, useAction } from "@/components/Feedback";
import { LABEL_SIZES_MM } from "@/components/LabelSheet";
import { ApiError, api } from "@/lib/api";
import {
  DEFAULT_LABEL_LAYOUT,
  PAGE_SIZES,
  planSheet,
  type LabelLayout,
  type PageSize,
} from "@/lib/labelPrint.ts";

type Saved = LabelLayout & { updated_at: string | null };

/** The numbers as typed, so a half-entered "7." is not snapped back to 7. */
type Draft = Omit<LabelLayout, "page_margin_mm" | "gap_mm"> & {
  page_margin_mm: string;
  gap_mm: string;
};

const toDraft = (layout: LabelLayout): Draft => ({
  page_size: layout.page_size,
  page_margin_mm: String(layout.page_margin_mm),
  gap_mm: String(layout.gap_mm),
  footprint_mm: layout.footprint_mm,
  show_header: layout.show_header,
  header_text: layout.header_text,
  show_reference: layout.show_reference,
});

/**
 * The organization's label sheet layout: what the printable sheet and PDF
 * carry besides the codes, and how far apart the codes are.
 */
export function LabelLayoutSettings({ organizationName }: { organizationName: string }) {
  const [saved, setSaved] = useState<Saved | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loadError, setLoadError] = useState("");
  const action = useAction();

  useEffect(() => {
    let live = true;
    api
      .get<Saved>("/v1/staff/label-layout")
      .then((layout) => {
        if (!live) return;
        setSaved(layout);
        setDraft(toDraft(layout));
      })
      .catch((e) => {
        if (live) setLoadError(e instanceof ApiError ? e.message : "Could not load the layout.");
      });
    return () => {
      live = false;
    };
  }, []);

  if (loadError) {
    return (
      <div className="card">
        <div className="alert error">{loadError}</div>
      </div>
    );
  }
  if (!draft) {
    return (
      <div className="card">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft({ ...draft, [key]: value });

  const layout: LabelLayout = {
    ...draft,
    page_margin_mm: Number(draft.page_margin_mm),
    gap_mm: Number(draft.gap_mm),
  };
  const numbersEntered = draft.page_margin_mm.trim() !== "" && draft.gap_mm.trim() !== "";
  let fit: ReturnType<typeof planSheet> | null = null;
  try {
    if (numbersEntered) fit = planSheet(1, layout);
  } catch {
    fit = null;
  }

  const save = (event: React.FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      const result = await api.patch<Saved>("/v1/staff/label-layout", layout);
      setSaved(result);
      setDraft(toDraft(result));
      return "Layout saved. Sheets and PDFs use it from now on.";
    });
  };

  return (
    <div className="card">
      <p className="muted" style={{ marginTop: 0 }}>
        Applies to every printable sheet, PDF and Excel file generated for{" "}
        {organizationName}. By default a sheet carries the codes and each one&rsquo;s
        serial number, nothing else. The codes themselves are the same whatever is
        chosen here.
      </p>
      <form onSubmit={save}>
        <div className="row" style={{ marginBottom: "0.9rem" }}>
          <label>
            <span>Page size</span>
            <select
              value={draft.page_size}
              onChange={(e) => set("page_size", e.target.value as PageSize)}
            >
              {(Object.keys(PAGE_SIZES) as PageSize[]).map((size) => (
                <option key={size} value={size}>
                  {PAGE_SIZES[size].name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Page margin (mm)</span>
            <input
              type="number"
              min={0}
              max={50}
              step={0.5}
              value={draft.page_margin_mm}
              onChange={(e) => set("page_margin_mm", e.target.value)}
              required
            />
          </label>
          <label>
            <span>Space between codes (mm)</span>
            <input
              type="number"
              min={0}
              max={100}
              step={0.5}
              value={draft.gap_mm}
              onChange={(e) => set("gap_mm", e.target.value)}
              required
            />
          </label>
          <label>
            <span>Default footprint</span>
            <select
              value={draft.footprint_mm}
              onChange={(e) => set("footprint_mm", Number(e.target.value))}
            >
              {LABEL_SIZES_MM.map((mm) => (
                <option key={mm} value={mm}>
                  {mm} mm
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.show_header}
            onChange={(e) => set("show_header", e.target.checked)}
          />
          Print a header at the top of each page
        </label>
        {draft.show_header && (
          <label style={{ maxWidth: 480 }}>
            <span>Header text</span>
            <input
              value={draft.header_text}
              onChange={(e) => set("header_text", e.target.value)}
              maxLength={120}
              placeholder="Batch {batch}"
            />
            <small className="muted">
              {"{batch}"} and {"{count}"} are filled in for each run. Left empty, the
              header reads &ldquo;Batch&rdquo; and the batch number. The PDF prints
              Latin characters only.
            </small>
          </label>
        )}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.show_reference}
            onChange={(e) => set("show_reference", e.target.checked)}
          />
          Print the serial number under each code (0042, from reference …-000042)
        </label>

        <p className="muted" style={{ fontSize: "0.85rem" }}>
          {!numbersEntered
            ? "Enter a margin and a spacing."
            : fit
              ? `${fit.perPage} codes per ${PAGE_SIZES[layout.page_size].name} page (${fit.columns} × ${fit.rows}) at ${layout.footprint_mm} mm. The space is measured between the edges of neighbouring codes, quiet zone included.`
              : "Not even one code fits on the page with this margin, footprint and spacing."}
          {saved?.updated_at && (
            <> Last changed {new Date(saved.updated_at).toLocaleString()}.</>
          )}
        </p>

        <div className="row" style={{ gap: "0.5rem" }}>
          <div className="shrink">
            <button type="submit" disabled={action.busy || !fit}>
              {action.busy ? "Saving…" : "Save layout"}
            </button>
          </div>
          <div className="shrink">
            <button
              type="button"
              className="secondary"
              disabled={action.busy}
              onClick={() => {
                action.clear();
                setDraft(toDraft(DEFAULT_LABEL_LAYOUT));
              }}
            >
              Restore defaults
            </button>
          </div>
        </div>
        <Feedback error={action.error} notice={action.notice} />
      </form>
    </div>
  );
}
