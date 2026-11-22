export type Role = 'worker' | 'caseworker' | 'admin';

export interface SessionUser {
  id: string;
  email?: string | null;
  phone?: string | null;
  role: Role;
  full_name?: string | null;
  preferred_language: 'en' | 'si' | 'ta';
  country_of_work?: string | null;
  is_active: boolean;
  created_at?: string;
}

export interface Session {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  expires_in?: number | null;
  user: SessionUser;
}

export interface PageMeta {
  request_id: string;
  page: number;
  page_size: number;
  total: number;
}

export interface PageResult<T> {
  items: T[];
  meta: PageMeta;
}

export interface DashboardMetrics {
  workers: number;
  active_journeys: number;
  verifications_this_week: number;
  high_risk_verifications: number;
  open_cases: number;
  open_cases_by_tier: { tier: number; count: number }[];
  overdue_checkins: number;
  agency_alerts: number;
}

export interface RecentActivity {
  kind: string;
  id: string;
  title: string;
  status: string;
  created_at: string;
}

export interface Dashboard {
  metrics: DashboardMetrics;
  recent_activity: RecentActivity[];
}

export type ComplaintStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'escalated'
  | 'resolved'
  | 'closed';

export interface Complaint {
  id: string;
  user_id: string;
  journey_id?: string | null;
  verification_id?: string | null;
  agency_id?: string | null;
  checkin_id?: string | null;
  title: string;
  description?: string | null;
  status: ComplaintStatus;
  triage_tier: number;
  assigned_to?: string | null;
  evidence?: Record<string, unknown>[];
  draft_text?: string | null;
  submitted_at?: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  worker_name?: string | null;
  worker_phone?: string | null;
  agency_name?: string | null;
}

export interface CaseNote {
  id: string;
  complaint_id: string;
  author_id?: string | null;
  author_name?: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface Verification {
  id: string;
  user_id: string;
  agency_id?: string | null;
  agency_name?: string | null;
  agency_registration_no?: string | null;
  job_title?: string | null;
  employer_name?: string | null;
  destination_country?: string | null;
  offered_salary?: number | null;
  currency?: string | null;
  status: string;
  risk_level?: string | null;
  risk_score?: number | null;
  findings?: { code?: string; message?: string; source?: string }[];
  evidence?: { document_id?: string; page?: number; quote?: string }[];
  engine_version?: string | null;
  analysis_run_id?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface Journey {
  id: string;
  user_id: string;
  agency_name?: string | null;
  destination_country?: string | null;
  employer_name?: string | null;
  job_title?: string | null;
  departure_date?: string | null;
  stage: string;
  consent_checkins: boolean;
  next_checkin_at?: string | null;
  created_at: string;
}

export interface Checkin {
  id: string;
  journey_id: string;
  user_id: string;
  due_at: string;
  channel: string;
  status: string;
  sent_at?: string | null;
  completed_at?: string | null;
  response?: Record<string, unknown> | null;
  risk_level?: string | null;
}

export interface DocumentMeta {
  id: string;
  user_id?: string;
  verification_id?: string | null;
  type: string;
  status: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  page_count?: number | null;
  sha256: string;
  created_at: string;
}

export interface CaseDetail {
  case: Complaint;
  worker?: User | null;
  journey?: Journey | null;
  verification?: Verification | null;
  checkin?: Checkin | null;
  documents: DocumentMeta[];
  notes: CaseNote[];
}

export interface User {
  id: string;
  role: Role;
  full_name?: string | null;
  phone?: string | null;
  preferred_language: string;
  country_of_work?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Agency {
  id: string;
  registration_no: string;
  name: string;
  license_no?: string | null;
  license_status: string;
  license_expires_on?: string | null;
  district?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LicenseHistory {
  id: string;
  agency_id: string;
  license_no?: string | null;
  status: string;
  issued_on?: string | null;
  expires_on?: string | null;
  job_categories?: string[] | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  actor_id?: string | null;
  actor_role?: string | null;
  action: string;
  entity_type?: string | null;
  entity_id?: string | null;
  ip_address?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ImportResult {
  snapshot_id?: string | null;
  snapshot_date: string;
  checksum: string;
  parsed: number;
  imported: number;
  errors: string[];
  duplicate_snapshot: boolean;
  dry_run: boolean;
}

export interface TraceResult {
  [key: string]: unknown;
}
