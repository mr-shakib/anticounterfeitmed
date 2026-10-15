"use client";

import { useEffect, useId, useRef } from "react";
import { Feedback } from "@/components/Feedback";

/**
 * A modal for anything that used to be `window.prompt` or `window.confirm`.
 *
 * The browser's own prompts cannot validate a number, cannot say what an
 * action will do in more than a line, and look like something a web page is
 * not supposed to show. This is the native `<dialog>`, so focus trapping and
 * Escape come from the browser rather than from code here.
 */
export function Dialog({
  open,
  title,
  onClose,
  children,
  wide = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={wide ? "dialog wide" : "dialog"}
      aria-labelledby={titleId}
      onCancel={(event) => {
        // Escape. Let the parent decide, so its state stays the truth.
        event.preventDefault();
        onClose();
      }}
    >
      {open && (
        <>
          <h2 id={titleId}>{title}</h2>
          {children}
        </>
      )}
    </dialog>
  );
}

/**
 * A dialog that asks for something and then does it.
 *
 * The form's own validation runs first (`required`, `min`, `max`), the error
 * from a refused request is shown inside the dialog rather than behind it, and
 * the dialog stays open until the action succeeds.
 */
export function ActionDialog({
  open,
  title,
  confirmLabel,
  danger = false,
  busy,
  error,
  onConfirm,
  onClose,
  children,
  wide = false,
}: {
  open: boolean;
  title: string;
  confirmLabel: string;
  wide?: boolean;
  danger?: boolean;
  busy: boolean;
  error?: string;
  onConfirm: () => void;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Dialog open={open} title={title} wide={wide} onClose={() => !busy && onClose()}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm();
        }}
      >
        {children}
        <Feedback error={error} />
        <div className="dialog-actions">
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className={danger ? "danger" : ""} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
