/**
 * The optional prescribing information a product can carry, in the order the
 * app shows it. Keys match `PRODUCT_INFORMATION_FIELDS` in the backend.
 */
export const INFORMATION_SECTIONS = [
  { key: "indications", label: "Indications", rows: 4 },
  { key: "therapeutic_class", label: "Therapeutic class", rows: 1 },
  { key: "pharmacology", label: "Pharmacology", rows: 4 },
  { key: "dosage_administration", label: "Dosage & administration", rows: 6 },
  { key: "interaction", label: "Interaction", rows: 2 },
  { key: "contraindications", label: "Contraindications", rows: 2 },
  { key: "side_effects", label: "Side effects", rows: 3 },
  { key: "pregnancy_lactation", label: "Pregnancy & lactation", rows: 3 },
  { key: "precautions_warnings", label: "Precautions & warnings", rows: 3 },
  { key: "overdose_effects", label: "Overdose effects", rows: 2 },
  { key: "reconstitution", label: "Reconstitution", rows: 4 },
  { key: "storage_conditions", label: "Storage conditions", rows: 2 },
] as const;

export type InformationKey = (typeof INFORMATION_SECTIONS)[number]["key"];
export type ProductInformation = Partial<Record<InformationKey, string>>;

/** Per section; the backend enforces the same limit. */
export const SECTION_MAX_CHARS = 4000;

/** Sections with text, dropping blanks, so an empty form sends nothing. */
export function filledInformation(info: ProductInformation): ProductInformation {
  const out: ProductInformation = {};
  for (const { key } of INFORMATION_SECTIONS) {
    const text = info[key]?.trim();
    if (text) out[key] = text;
  }
  return out;
}
