/**
 * Client for the staff API.
 *
 * Two things every call depends on:
 *
 * - `credentials: "include"`, because staff auth is a session cookie;
 * - the CSRF token on writes. Django enforces it, and omitting it produces a
 *   403 that looks like a permissions failure but is not.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message);
  }

  /** A request refused because the role or the second factor is insufficient. */
  get isForbidden() {
    return this.status === 403;
  }
}

/** Where the portal is mounted. Empty in development, "/staff" when deployed. */
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** Prefixes an API path with the mount point, so /v1/... resolves correctly. */
function apiPath(path: string): string {
  return `${BASE_PATH}${path}`;
}

/**
 * A portal page's full URL path, for the few places that leave Next's router
 * (a hard navigation). `Link` and `router` add the mount point themselves;
 * `window.location` does not, and "/login" alone lands on the hub's 404.
 */
export function portalPath(path: string): string {
  return `${BASE_PATH}${path}`;
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && method !== "HEAD") {
    headers["X-CSRFToken"] = csrfToken();
  }

  const response = await fetch(apiPath(path), {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = undefined;
  try {
    payload = text ? JSON.parse(text) : undefined;
  } catch {
    payload = text;
  }

  if (!response.ok) {
    const data = (payload ?? {}) as Record<string, unknown>;
    throw new ApiError(
      response.status,
      String(data.code ?? "ERROR"),
      String(data.detail ?? fieldErrors(data) ?? response.statusText),
      payload,
    );
  }
  return payload as T;
}

/**
 * A validation refusal as one readable sentence.
 *
 * Django REST framework reports these per field, with no `detail`, so without
 * this a form refusal surfaced as the bare words "Bad Request".
 */
function fieldErrors(data: Record<string, unknown>): string | undefined {
  const parts: string[] = [];
  for (const [field, value] of Object.entries(data)) {
    if (field === "code") continue;
    const messages = (Array.isArray(value) ? value : [value]).map(String).join(" ");
    if (!messages) continue;
    const name = field.replace(/_/g, " ");
    parts.push(
      field === "non_field_errors"
        ? messages
        : `${name.charAt(0).toUpperCase()}${name.slice(1)}: ${messages}`,
    );
  }
  return parts.length ? parts.join(" ") : undefined;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
};

/**
 * Ensures a CSRF cookie exists before the first write.
 *
 * Django only sets it on a response that needs it, so a portal that opens
 * straight onto a form would otherwise post without one.
 */
export async function primeCsrf(): Promise<void> {
  try {
    await fetch(apiPath("/v1/staff/me"), { credentials: "include" });
  } catch {
    /* the caller will surface the real failure */
  }
}

// --- shapes returned by the API ---------------------------------------------

export type Membership = {
  membership_id: string;
  username: string;
  role: "PLATFORM_ADMIN" | "RELEASE_MANAGER" | "MANUFACTURER_STAFF";
  organization: {
    id: string;
    name: string;
    type: string;
    approval_status: string;
    is_suspended: boolean;
  };
  /** A code is needed now, because one is enrolled. */
  mfa_required: boolean;
  /** Policy makes enrolling a precondition for this role. */
  mfa_enrolment_required: boolean;
  mfa_enrolled: boolean;
  mfa_verified: boolean;
  /** Signed in with an administrator's temporary password; must replace it. */
  password_change_required: boolean;
};

export type Product = {
  id: string;
  brand: string;
  generic: string;
  strength: string;
  dosage_form: string;
  pack_description: string;
  registration_reference: string;
  /** Optional prescribing information, keyed by section. */
  information: Record<string, string>;
};

export type Batch = {
  id: string;
  product: string;
  product_brand: string;
  batch_number: string;
  manufactured_on: string;
  expires_on: string;
  planned_unit_count: number;
  is_recalled: boolean;
  recalled_at: string | null;
  recall_notice: string;
  /** Present on the batch list only. */
  progress?: BatchProgress;
};

/** Where a batch stands, as the batch list reports it. */
export type BatchProgress = {
  units_total: number;
  counts_by_lifecycle: Record<string, number>;
  units_ready: number;
};

export type Unit = {
  id: string;
  external_reference: string;
  lifecycle: string;
  is_blocked: boolean;
  blocked_reason: string;
  version: number;
  activated_at: string | null;
  redeemed_at: string | null;
};

/// Progress through the manufacturing records a batch needs before activation.
///
/// Counts are of units, not events, and every one is a manufacturer assertion
/// rather than scan evidence captured by this system.
export type BatchUnits = {
  counts_by_lifecycle: Record<string, number>;
  counts_by_step: Record<string, number>;
  units_ready: number;
  /** The subset of PRINTED records this system observed, rather than was told. */
  units_scan_verified: number;
  units_blocked: number;
  /** How many units match the search, of which `units` is one page. */
  units_matching: number;
  offset: number;
  units: Unit[];
};

export type ActivationJob = {
  id: string;
  approval_id: string;
  status: string;
  requested: number;
  succeeded: number;
  failed: number;
  created_at: string;
  finished_at: string | null;
  failures: { unit_id: string; external_reference: string; reason: string }[];
  /** Whole-batch runs only: units that were not candidates, by state. */
  not_attempted?: Record<string, number>;
};

export type PrintJob = {
  id: string;
  batch: string;
  planned_count: number;
  issued_count: number;
  status: string;
  reconciled_at: string | null;
  reconciled_printed: number | null;
  reconciled_rejected: number | null;
  export_available: boolean;
  export_expires_at: string | null;
  export_deleted_at: string | null;
  created_at: string;
};

export type LabelExport = {
  print_job: PrintJob;
  label_export: {
    external_reference: string;
    /** The symbol to print. Drawn by lib/labelSymbol.ts; never a URL. */
    qr: { version: number; error_correction: string; data_codewords: string };
  }[];
  export_notice: string;
};

export type Organization = {
  id: string;
  name: string;
  type: string;
  approval_status: string;
  is_suspended: boolean;
  suspension_reason: string;
  contact_email: string;
  contact_phone: string;
  /** Holds an active key to sign its units' credentials. */
  has_signing_key: boolean;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  action: string;
  organization: string | null;
  actor: string | null;
  unit_id: string | null;
  batch_id: string | null;
  reason: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type Report = {
  case_number: string;
  reason: string;
  status: string;
  organization: string | null;
  unit_id: string | null;
  external_reference: string;
  assigned_to: string | null;
  created_at: string;
};

/** A row in the administrator's staff list. */
export type StaffRow = {
  membership_id: string;
  username: string;
  organization: string;
  organization_id: string;
  role: Membership["role"];
  is_enabled: boolean;
  disabled_at: string | null;
  password_change_required: boolean;
  mfa_required: boolean;
  mfa_enrolled: boolean;
};

export type Dashboard = {
  organizations_pending: number;
  organizations_suspended: number;
  activation_jobs_with_failures: number;
  receipts_pending: number;
  receipts_failed: number;
  reports_open: number;
  first_verifications: number;
  repeat_checks: number;
};
