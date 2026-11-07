import { apiClient } from "../../lib/api";

export type PatDocument = {
  cdate: string;
  created_by: string;
  expires_at: string | null;
  id: string;
  mdate: string;
  name: string;
  revoked_at: string | null;
  subject_id: string;
  token?: string;
};

type PatsResponse = {
  pats: PatDocument[];
};

type CreatedPatResponse = {
  pat: PatDocument & { token: string };
};

export type PatActionResult = {
  id: string;
  mdate: string;
  revoked_at?: string | null;
  token?: string;
};

type PatActionResponse = {
  pat: PatActionResult;
};

export type CreatePatPayload = {
  expires_at?: string | null;
  name: string;
  subject_id: string;
};

export function listPats(signal?: AbortSignal) {
  return apiClient.get<PatsResponse>("/auth/pats/", { signal }).then((payload) => payload.pats);
}

export function createPat(pat: CreatePatPayload) {
  return apiClient.post<CreatedPatResponse>("/auth/pats/", { pat }).then((payload) => payload.pat);
}

export function revokePat(patId: string) {
  return apiClient.post<PatActionResponse>(`/auth/pats/${encodeURIComponent(patId)}/revoke/`).then((payload) => payload.pat);
}

export function rotatePat(patId: string) {
  return apiClient.post<PatActionResponse>(`/auth/pats/${encodeURIComponent(patId)}/rotate/`).then((payload) => payload.pat);
}
