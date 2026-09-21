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
      String(data.detail ?? response.statusText),
      payload,
    );
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
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
};

export type Product = {
  id: string;
  brand: string;
  generic: string;
  strength: string;
  dosage_form: string;
  pack_description: string;
  registration_reference: string;
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
  units: Unit[];
};

export type ActivationJob = {
  id: string;
  approval_id: string;
  status: string;
  requested: number;
  succeeded: number;
  failed: number;
  finished_at: string | null;
  failures: { unit_id: string; reason: string }[];
};

export type PrintJob = {
  id: string;
  batch: string;
  planned_count: number;
  issued_count: number;
  status: string;
  reconciled_at: string | null;
  export_available: boolean;
  export_expires_at: string | null;
  export_deleted_at: string | null;
  created_at: string;
};

export type LabelExport = {
  print_job: PrintJob;
  label_export: { external_reference: string; qr_url: string }[];
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

export type Membership2 = {
  membership_id: string;
  username: string;
  organization: string;
  role: string;
  is_enabled: boolean;
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
