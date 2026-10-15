"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, Batch, Product, api } from "@/lib/api";
import { BatchTable, waitingOnMe } from "@/components/BatchTable";
import { Feedback, useAction } from "@/components/Feedback";
import { useSession } from "@/components/Session";

const EMPTY = {
  product: "", batch_number: "", manufactured_on: "",
  expires_on: "", planned_unit_count: "",
};

export default function BatchesPage() {
  const { membership } = useSession();
  const canRelease = membership?.role === "RELEASE_MANAGER";
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const action = useAction();

  async function load() {
    try {
      const [b, p] = await Promise.all([
        api.get<Batch[]>("/v1/staff/batches"),
        api.get<Product[]>("/v1/staff/products"),
      ]);
      setBatches(b);
      setProducts(p);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load.");
    }
  }

  useEffect(() => { void load(); }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void action.run(async () => {
      const batch = await api.post<Batch>("/v1/staff/batches", {
        ...form,
        planned_unit_count: Number(form.planned_unit_count),
      });
      setForm({ ...EMPTY });
      setCreating(false);
      await load();
      return `Batch ${batch.batch_number} created. Open it to generate its labels.`;
    });
  };

  const showForm = creating || (batches !== null && batches.length === 0);
  const mine = (batches ?? []).filter((b) => waitingOnMe(b, canRelease));
  const shown = filter === "mine" ? mine : batches ?? [];

  return (
    <>
      <div className="title-row">
        <h1>Batches</h1>
        {!showForm && (
          <button onClick={() => { action.clear(); setCreating(true); }}>New batch</button>
        )}
      </div>
      <p className="muted">
        Each batch moves through four steps: labels, printing, QC and coating,
        then activation by a release manager.
      </p>
      {loadError && <div className="alert error">{loadError}</div>}

      {showForm && (
        <div className="card">
          <h2>Create a batch</h2>
          {products.length === 0 ? (
            <p className="muted">
              A batch belongs to a product. <Link href="/products">Add a product</Link>{" "}
              first.
            </p>
          ) : (
            <form onSubmit={submit}>
              <div className="row">
                <label>
                  <span>Product</span>
                  <select
                    value={form.product}
                    onChange={(e) => setForm({ ...form, product: e.target.value })}
                    required
                  >
                    <option value="">Choose…</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.brand} {p.strength} — {p.pack_description}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Manufacturer batch number</span>
                  <input
                    value={form.batch_number}
                    onChange={(e) => setForm({ ...form, batch_number: e.target.value })}
                    required
                  />
                </label>
                <label>
                  <span>Planned units (strips)</span>
                  <input
                    type="number" min={1}
                    value={form.planned_unit_count}
                    onChange={(e) => setForm({ ...form, planned_unit_count: e.target.value })}
                    required
                  />
                </label>
              </div>
              <div className="row">
                <label>
                  <span>Manufactured on</span>
                  <input
                    type="date" value={form.manufactured_on}
                    onChange={(e) => setForm({ ...form, manufactured_on: e.target.value })}
                    required
                  />
                </label>
                <label>
                  <span>Expires on — the final valid date</span>
                  <input
                    type="date" value={form.expires_on}
                    min={form.manufactured_on || undefined}
                    onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
                    required
                  />
                </label>
              </div>
              <p className="muted">
                If the printed label shows only a month and year, enter the intended
                final valid date. The system does not guess it.
              </p>
              <div className="form-actions">
                <button type="submit" disabled={action.busy}>
                  {action.busy ? "Creating…" : "Create batch"}
                </button>
                {batches !== null && batches.length > 0 && (
                  <button type="button" className="secondary" onClick={() => setCreating(false)}>
                    Cancel
                  </button>
                )}
              </div>
              <Feedback error={action.error} />
            </form>
          )}
        </div>
      )}
      <Feedback notice={action.notice} />

      {batches !== null && batches.length > 0 && (
        <>
          <div className="segmented" role="group" aria-label="Show">
            <button
              className={filter === "all" ? "selected" : ""}
              onClick={() => setFilter("all")}
            >
              All batches ({batches.length})
            </button>
            <button
              className={filter === "mine" ? "selected" : ""}
              onClick={() => setFilter("mine")}
            >
              Waiting on you ({mine.length})
            </button>
          </div>
          <BatchTable batches={shown} canRelease={canRelease} />
        </>
      )}
    </>
  );
}
