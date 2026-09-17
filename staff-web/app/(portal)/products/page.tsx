"use client";

import { useEffect, useState } from "react";
import { ApiError, Product, api } from "@/lib/api";

const EMPTY = {
  brand: "", generic: "", strength: "", dosage_form: "",
  pack_description: "", registration_reference: "",
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setProducts(await api.get<Product[]>("/v1/staff/products"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load products.");
    }
  }

  useEffect(() => { void load(); }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post<Product>("/v1/staff/products", form);
      setForm({ ...EMPTY });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof EMPTY) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  });

  return (
    <>
      <h1>Products</h1>
      <p className="muted">
        These values are frozen into a signed credential when a unit is
        activated. Editing a product afterwards does not change what was already
        issued.
      </p>
      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Add a product</h2>
        <form onSubmit={submit}>
          <div className="row">
            <label><span>Brand</span><input {...field("brand")} required /></label>
            <label><span>Generic name</span><input {...field("generic")} required /></label>
            <label><span>Strength</span><input {...field("strength")} placeholder="500 mg" required /></label>
          </div>
          <div className="row">
            <label><span>Dosage form</span><input {...field("dosage_form")} placeholder="Tablet" required /></label>
            <label>
              <span>Pack description (the unit as sold)</span>
              <input {...field("pack_description")} placeholder="Strip of 10 tablets" required />
            </label>
            <label>
              <span>Registration reference (optional)</span>
              <input {...field("registration_reference")} />
            </label>
          </div>
          <button type="submit" disabled={busy}>{busy ? "Saving…" : "Add product"}</button>
        </form>
      </div>

      <table>
        <thead>
          <tr><th>Brand</th><th>Generic</th><th>Strength</th><th>Form</th><th>Pack</th></tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.id}>
              <td>{p.brand}</td><td>{p.generic}</td><td>{p.strength}</td>
              <td>{p.dosage_form}</td><td>{p.pack_description}</td>
            </tr>
          ))}
          {products.length === 0 && (
            <tr><td colSpan={5} className="muted">No products yet.</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
