"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, Batch, Product, api } from "@/lib/api";

export default function BatchesPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [form, setForm] = useState({
    product: "", batch_number: "", manufactured_on: "",
    expires_on: "", planned_unit_count: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [b, p] = await Promise.all([
        api.get<Batch[]>("/v1/staff/batches"),
        api.get<Product[]>("/v1/staff/products"),
      ]);
      setBatches(b);
      setProducts(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post<Batch>("/v1/staff/batches", {
        ...form,
        planned_unit_count: Number(form.planned_unit_count),
      });
      setForm({ product: "", batch_number: "", manufactured_on: "", expires_on: "", planned_unit_count: "" });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the batch.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Batches</h1>
      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Create a batch</h2>
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
                onChange={(e) => setForm({ ...form, expires_on: e.target.value })}
                required
              />
            </label>
          </div>
          <p className="muted">
            If the printed label shows only a month and year, enter the intended
            final valid date. The system does not guess it.
          </p>
          <button type="submit" disabled={busy || products.length === 0}>
            {busy ? "Creating…" : "Create batch"}
          </button>
          {products.length === 0 && (
            <p className="muted">Add a product first.</p>
          )}
        </form>
      </div>

      <table>
        <thead>
          <tr><th>Batch</th><th>Product</th><th>Manufactured</th><th>Expires</th><th>Planned</th><th>Status</th></tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id}>
              <td><Link href={`/batches/${b.id}`}>{b.batch_number}</Link></td>
              <td>{b.product_brand}</td>
              <td>{b.manufactured_on}</td>
              <td>{b.expires_on}</td>
              <td>{b.planned_unit_count}</td>
              <td>
                {b.is_recalled
                  ? <span className="badge danger">recalled</span>
                  : <span className="badge ok">active</span>}
              </td>
            </tr>
          ))}
          {batches.length === 0 && (
            <tr><td colSpan={6} className="muted">No batches yet.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
