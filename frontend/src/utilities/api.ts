import { apiBaseUrl } from "./config";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: string[];

  constructor(status: number, code: string, message: string, fields: string[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "request_failed", "The LabLink API could not be reached.");
  }

  const text = await response.text();
  let data: unknown = null;
  if (text.length > 0) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      throw new ApiError(response.status, "request_failed", "The request could not be completed.");
    }
  }
  if (!response.ok) {
    const body = data as { error?: string; message?: string; fields?: string[] } | null;
    const fields = Array.isArray(body?.fields) ? body.fields : [];
    let message = body?.message ?? "The request could not be completed.";
    if (response.status === 422) {
      if (fields.some((field) => field === "start" || field === "end" || field.endsWith(".start") || field.endsWith(".end"))) {
        message = "Pick a start time on a 15-minute mark, with a length between 15 minutes and 8 hours.";
      } else if (fields.includes("purpose")) {
        message = "Keep the purpose note under 200 characters.";
      } else if (fields.includes("project_id") || fields.includes("equipment_id")) {
        message = "Choose an item and a free time, then try again.";
      } else {
        message = "Pick a start time on a 15-minute mark, with a length between 15 minutes and 8 hours.";
      }
    }
    throw new ApiError(response.status, body?.error ?? "request_failed", message, fields);
  }
  return data as T;
}

export type EquipmentStatus = "available" | "maintenance" | "retired";

export type Specification = {
  name: string;
  value: string;
  unit: string | null;
};

export type SafetyPrerequisite = {
  code: string;
  description: string;
};

export type ResourceKind = "equipment" | "lab-station" | "kit";

export type Equipment = {
  id: string;
  name: string;
  category: string;
  lab_id: string;
  department_id: string;
  description: string;
  specifications: Specification[];
  status: EquipmentStatus;
  safety_prerequisites: SafetyPrerequisite[];
  kind?: ResourceKind;
};

export type EquipmentListResponse = {
  items: Equipment[];
  total: number;
  limit: number;
  offset: number;
  source: "synthetic";
};

export type EquipmentMatch = {
  equipment_id: string;
  name: string;
  department_id: string;
  score: number;
  suitability: "fully_suitable" | "partially_suitable" | "unsuitable";
  matched_requirements: string[];
  unmet_requirements: string[];
  explanation: string;
};

export type MatchListResponse = {
  project_id: string;
  items: EquipmentMatch[];
  total: number;
  limit: number;
  source: "synthetic";
};

export type TimeInterval = {
  start: string;
  end: string;
};

export type AvailabilityResponse = {
  equipment_id: string;
  start: string;
  end: string;
  available: TimeInterval[];
  unavailable: TimeInterval[];
  source: "synthetic";
  demo: true;
};

export type BookingView = {
  id: string;
  equipment_id: string;
  equipment_name?: string;
  kind?: ResourceKind;
  project_id: string;
  purpose?: string;
  start: string;
  end: string;
  status: string;
  user_id: string;
  demo: true;
};

export type BookingListResponse = {
  items: BookingView[];
  demo_user_id: string;
  source: "synthetic";
  demo: true;
};

export type EquipmentQuery = {
  search?: string;
  department?: string;
  category?: string;
  status?: string;
  kind?: ResourceKind;
};

export function listEquipment(query: EquipmentQuery = {}): Promise<EquipmentListResponse> {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.department) params.set("department", query.department);
  if (query.category) params.set("category", query.category);
  if (query.status) params.set("status", query.status);
  if (query.kind) params.set("kind", query.kind);
  params.set("limit", "100");
  const suffix = params.toString();
  return request(`/equipment?${suffix}`);
}

export function getEquipment(id: string): Promise<Equipment> {
  return request(`/equipment/${id}`);
}

export function getMatches(projectId: string): Promise<MatchListResponse> {
  return request(`/projects/${projectId}/equipment-matches?limit=100`);
}

export function getAvailability(equipmentId: string, date: string): Promise<AvailabilityResponse> {
  return request(`/equipment/${equipmentId}/availability?date=${date}`);
}

export function listBookings(): Promise<BookingListResponse> {
  return request("/bookings");
}

export function createBooking(body: {
  equipment_id: string;
  project_id: string;
  purpose?: string;
  start: string;
  end: string;
}): Promise<BookingView> {
  const payload: Record<string, string> = {
    equipment_id: body.equipment_id,
    project_id: body.project_id,
    start: body.start,
    end: body.end,
  };
  const purpose = body.purpose?.trim() ?? "";
  if (purpose) {
    payload.purpose = purpose;
  }
  return request("/bookings", { method: "POST", body: JSON.stringify(payload) });
}

export type AccessRequestView = {
  id: string;
  equipment_id: string;
  project_id: string;
  status: string;
  justification: string;
  created_at: string;
  start: string | null;
  end: string | null;
  user_id: string | null;
  approvals: {
    id: string;
    faculty_id: string;
    decision: string;
    comments: string;
    decided_at: string;
  }[];
  booking_id: string | null;
  demo: true;
};

export type AccessRequestListResponse = {
  items: AccessRequestView[];
  demo_user_id: string;
  demo_role: string;
  source: "synthetic";
  demo: true;
};

export type ConflictItem = {
  request_id: string;
  project_id: string;
  requester_department_id: string;
  requester_user_id: string | null;
  eligible: boolean;
  feasible: boolean;
  provisional: boolean;
  score: number | null;
  rank: number;
  components: Record<string, number | null>;
  missing_inputs: string[];
  explanation: string;
  alternatives: string[];
};

export type ConflictListResponse = {
  equipment_id: string;
  items: ConflictItem[];
  weights: Record<string, number>;
  source: "synthetic";
  demo: true;
  note: string;
};

export function listAccessRequests(): Promise<AccessRequestListResponse> {
  return request("/access-requests");
}

export function createAccessRequest(body: {
  equipment_id: string;
  project_id: string;
  justification: string;
  start: string;
  end: string;
}): Promise<AccessRequestView> {
  return request("/access-requests", { method: "POST", body: JSON.stringify(body) });
}

export function decideAccessRequest(
  id: string,
  decision: "approve" | "reject",
  comments: string,
): Promise<AccessRequestView> {
  return request(`/access-requests/${id}/${decision}`, {
    method: "POST",
    body: JSON.stringify({ comments }),
  });
}

export function getConflicts(equipmentId: string): Promise<ConflictListResponse> {
  return request(`/equipment/${equipmentId}/conflicts`);
}

export type MeResponse = {
  id: string;
  role: "student" | "faculty" | "admin";
  department_id: string;
  auth: "firebase" | "test";
  demo: true;
};

export function getMe(): Promise<MeResponse> {
  return request("/me");
}

export function bootstrapProfile(departmentId: string): Promise<MeResponse> {
  return request("/users/bootstrap", {
    method: "POST",
    body: JSON.stringify({ department_id: departmentId }),
  });
}

export type ExtractedRequirement = {
  name: string;
  value: string;
  unit: string | null;
  mandatory: boolean;
  comparison: "equal" | "at_least" | "at_most";
};

export type CitationView = {
  title: string;
  section: string;
  doc_id: string;
  synthetic: true;
};

export type ProjectRequirementsResponse = {
  summary: string;
  requirements: ExtractedRequirement[];
  matches: EquipmentMatch[];
  warnings: string[];
  source: "gemini";
  demo: true;
};

export type AssistantQueryResponse = {
  answer: string;
  citations: CitationView[];
  equipment_ids: string[];
  evidence_insufficient: boolean;
  refused: boolean;
  source: "gemini" | "catalog" | "refused";
  demo: true;
};

export type EquipmentExplanationResponse = {
  equipment_id: string;
  answer: string;
  citations: CitationView[];
  match: EquipmentMatch | null;
  source: "gemini";
  demo: true;
};

export function extractProjectRequirements(description: string): Promise<ProjectRequirementsResponse> {
  return request("/ai/project-requirements", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

export function queryAssistant(question: string): Promise<AssistantQueryResponse> {
  return request("/ai/assistant/query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export type RecommendedSlot = {
  equipment_id: string;
  start: string;
  end: string;
  suitability: "fully_suitable" | "partially_suitable" | "unsuitable";
  explanation: string;
  constraints: string[];
  advisory: true;
};

export type AlternativeEquipment = {
  equipment_id: string;
  name: string;
  suitability: "fully_suitable" | "partially_suitable" | "unsuitable";
  mandatory_ok: boolean;
  explanation: string;
  slots: RecommendedSlot[];
};

export type SchedulingResponse = {
  equipment_id: string;
  slots: RecommendedSlot[];
  alternatives: AlternativeEquipment[];
  constraints: string[];
  waitlist_eligible: boolean;
  source: "synthetic";
  demo: true;
};

export type WaitlistView = {
  id: string;
  equipment_id: string;
  project_id: string;
  duration_minutes: number;
  preferred_start: string;
  preferred_end: string;
  flexibility_minutes: number;
  status: "waiting" | "offered" | "fulfilled" | "cancelled" | "expired";
  created_at: string;
  updated_at: string;
  offer_id: string | null;
  offered_start: string | null;
  offered_end: string | null;
  offer_expires_at: string | null;
  rank: number | null;
  eligible: boolean | null;
  feasible: boolean | null;
  provisional: boolean | null;
  explanation: string | null;
  demo: true;
};

export type WaitlistListResponse = {
  items: WaitlistView[];
  source: "synthetic";
  demo: true;
};

export function getSchedulingRecommendations(body: {
  equipment_id: string;
  project_id: string;
  duration_minutes: number;
  preferred_start: string;
  preferred_end: string;
  flexibility_minutes: number;
  increment_minutes: number;
}): Promise<SchedulingResponse> {
  return request("/scheduling/recommendations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function joinWaitlist(body: {
  equipment_id: string;
  project_id: string;
  duration_minutes: number;
  preferred_start: string;
  preferred_end: string;
  flexibility_minutes: number;
}): Promise<WaitlistView> {
  return request("/waitlist", { method: "POST", body: JSON.stringify(body) });
}

export function listWaitlist(): Promise<WaitlistListResponse> {
  return request("/waitlist");
}

export function cancelWaitlist(id: string): Promise<WaitlistView> {
  return request(`/waitlist/${id}/cancel`, { method: "POST" });
}

export function acceptWaitlistOffer(id: string): Promise<BookingView> {
  return request(`/waitlist/${id}/accept`, { method: "POST" });
}

export function cancelBooking(id: string): Promise<BookingView> {
  return request(`/bookings/${id}/cancel`, { method: "POST" });
}

export type UtilizationView = {
  percent: number | null;
  occupied_minutes: number;
  available_minutes: number | null;
  unavailable_reason: string | null;
  capacity_per_slot: 1;
};

export type AnalyticsCounts = {
  equipment_total: number;
  equipment_active: number;
  confirmed_bookings: number;
  pending_requests: number;
  waitlist_waiting: number;
  waitlist_offered: number;
  conflicts: number;
};

export type EquipmentAnalytics = {
  equipment_id: string;
  name: string;
  department_id: string;
  category: string;
  occupied_minutes: number;
  confirmed_bookings: number;
  pending_requests: number;
  waitlist_waiting: number;
  underused: boolean;
  utilization: UtilizationView;
};

export type DepartmentAnalytics = {
  department_id: string;
  occupied_minutes: number;
  confirmed_bookings: number;
  pending_requests: number;
  waitlist_waiting: number;
  utilization: UtilizationView;
};

export type AnalyticsOverview = {
  start: string;
  end: string;
  counts: AnalyticsCounts;
  utilization: UtilizationView;
  most_booked: EquipmentAnalytics[];
  demand_by_category: { category: string; pending_requests: number; waitlist_waiting: number; confirmed_bookings: number }[];
  waitlist_demand: EquipmentAnalytics[];
  approval_turnaround: {
    sample_size: number;
    median_hours: number | null;
    unavailable_reason: string | null;
  };
  source: "synthetic";
  demo: true;
};

export type DepartmentAnalyticsResponse = {
  start: string;
  end: string;
  items: DepartmentAnalytics[];
  source: "synthetic";
  demo: true;
};

export type EquipmentAnalyticsResponse = {
  start: string;
  end: string;
  items: EquipmentAnalytics[];
  source: "synthetic";
  demo: true;
};

function analyticsQuery(start: string, end: string): string {
  const params = new URLSearchParams({ start, end });
  return params.toString();
}

export function getAnalyticsOverview(start: string, end: string): Promise<AnalyticsOverview> {
  return request(`/analytics/overview?${analyticsQuery(start, end)}`);
}

export function getAnalyticsDepartments(start: string, end: string): Promise<DepartmentAnalyticsResponse> {
  return request(`/analytics/departments?${analyticsQuery(start, end)}`);
}

export function getAnalyticsEquipment(start: string, end: string): Promise<EquipmentAnalyticsResponse> {
  return request(`/analytics/equipment?${analyticsQuery(start, end)}`);
}

export function explainEquipment(
  equipmentId: string,
  projectDescription?: string,
): Promise<EquipmentExplanationResponse> {
  const body: { equipment_id: string; project_description?: string } = {
    equipment_id: equipmentId,
  };
  if (projectDescription) {
    body.project_description = projectDescription;
  }
  return request("/ai/equipment-explanation", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
