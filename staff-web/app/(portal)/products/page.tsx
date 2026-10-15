"use client";

import { useEffect, useState } from "react";
import { ApiError, Product, api } from "@/lib/api";
import { ActionDialog } from "@/components/Dialog";
import { Feedback, useAction } from "@/components/Feedback";
import {
  INFORMATION_SECTIONS,
  ProductInformation,
  SECTION_MAX_CHARS,
  filledInformation,
} from "@/lib/productInformation";

const EMPTY = {
  brand: "", generic: "", strength: "", dosage_form: "",
  pack_description: "", registration_reference: "",
};

/** The twelve optional sections, each with a character count. */
function InformationFields({
  value,
  onChange,
}: {
  value: ProductInformation;
  onChange: (next: ProductInformation) => void;
}) {
  return (
    <div className="info-fields">
      {INFORMATION_SECTIONS.map(({ key, label, rows }) => {
        const length = value[key]?.length ?? 0;
        return (
          <label key={key}>
            <span>
              {label}
              {length > 0 && (
                <span className={`count ${length > SECTION_MAX_CHARS ? "over" : ""}`}>
                  {length} / {SECTION_MAX_CHARS}
                </span>
              )}
            </span>
            <textarea
              rows={rows}
              value={value[key] ?? ""}
              maxLength={SECTION_MAX_CHARS}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
            />
          </label>
        );
      })}
    </div>
  );
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [information, setInformation] = useState<ProductInformation>({});
  const [adding, setAdding] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Product | null>(null);
  const [draft, setDraft] = useState<ProductInformation>({});
  const create = useAction();
  const edit = useAction();

  async function load() {
    try {
      setProducts(await api.get<Product[]>("/v1/staff/products"));
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Could not load products.");
    }
  }

  useEffect(() => { void load(); }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice("");
    void create.run(async () => {
      const product = await api.post<Product>("/v1/staff/products", {
        ...form,
        information: filledInformation(information),
      });
      setForm({ ...EMPTY });
      setInformation({});
      setAdding(false);
      setNotice(`${product.brand} added.`);
      await load();
    });
  };

  const saveInformation = () =>
    edit.run(async () => {
      if (!editing) return;
      await api.patch<Product>(`/v1/staff/products/${editing.id}/information`, {
        information: filledInformation(draft),
      });
      setNotice(`Information for ${editing.brand} saved. The app shows it from the next scan.`);
      setEditing(null);
      await load();
    });

  const field = (key: keyof typeof EMPTY) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [key]: e.target.value }),
  });

  const showForm = adding || (products !== null && products.length === 0);
  const filledCount = Object.keys(filledInformation(information)).length;

  return (
    <>
      <div className="title-row">
        <h1>Products</h1>
        {!showForm && (
          <button onClick={() => { create.clear(); setAdding(true); }}>Add product</button>
        )}
      </div>
      <p className="muted">
        Brand, strength and the other details are frozen into a signed credential
        when a unit is activated, and cannot be edited afterwards. The optional
        medicine information can be updated at any time; the app shows the
        current version, marked as provided by the manufacturer.
      </p>
      {loadError && <div className="alert error">{loadError}</div>}

      {showForm && (
        <div className="card">
          <h2>Add a product</h2>
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

            <details className="info-section">
              <summary>
                Medicine information{" "}
                <span className="muted">
                  — optional{filledCount > 0 ? `, ${filledCount} section(s) filled` : ""}
                </span>
              </summary>
              <p className="muted" style={{ marginTop: 0 }}>
                Indications, dosage, side effects and the rest, as on the package
                insert. Shown in the app after a scan, labelled as provided by the
                manufacturer. Leave any section empty to omit it.
              </p>
              <InformationFields value={information} onChange={setInformation} />
            </details>

            <div className="form-actions">
              <button type="submit" disabled={create.busy}>
                {create.busy ? "Saving…" : "Add product"}
              </button>
              {products !== null && products.length > 0 && (
                <button type="button" className="secondary" onClick={() => setAdding(false)}>
                  Cancel
                </button>
              )}
            </div>
            <Feedback error={create.error} />
          </form>
        </div>
      )}
      <Feedback notice={notice} />

      <table>
        <thead>
          <tr>
            <th>Brand</th><th>Generic</th><th>Strength</th><th>Form</th><th>Pack</th>
            <th>Information</th><th></th>
          </tr>
        </thead>
        <tbody>
          {(products ?? []).map((p) => {
            const sections = Object.keys(p.information ?? {}).length;
            return (
              <tr key={p.id}>
                <td>{p.brand}</td><td>{p.generic}</td><td>{p.strength}</td>
                <td>{p.dosage_form}</td><td>{p.pack_description}</td>
                <td>
                  {sections > 0
                    ? <span className="badge ok">{sections} section(s)</span>
                    : <span className="muted">none</span>}
                </td>
                <td>
                  <button
                    onClick={() => {
                      edit.clear();
                      setNotice("");
                      setDraft({ ...(p.information ?? {}) });
                      setEditing(p);
                    }}
                  >
                    {sections > 0 ? "Edit information…" : "Add information…"}
                  </button>
                </td>
              </tr>
            );
          })}
          {products !== null && products.length === 0 && (
            <tr><td colSpan={7} className="muted">No products yet.</td></tr>
          )}
        </tbody>
      </table>

      <ActionDialog
        open={editing !== null}
        wide
        title={`Medicine information — ${editing?.brand ?? ""}`}
        confirmLabel="Save information"
        busy={edit.busy}
        error={edit.error}
        onConfirm={() => void saveInformation()}
        onClose={() => setEditing(null)}
      >
        <p className="muted">
          All optional. The app shows the saved version from the next scan,
          labelled as provided by the manufacturer. Every change is recorded.
        </p>
        <InformationFields value={draft} onChange={setDraft} />
      </ActionDialog>
    </>
  );
}
