import { apiClient } from "./api";
import type { ReferenceValue } from "./references";

export type AuthenticatedUser = {
  admin?: boolean;
  avatar?: unknown;
  description?: string;
  entity: string;
  groups?: ReferenceValue[];
  id: string;
  login: string;
  primary_group?: ReferenceValue;
  role?: string;
  superuser?: boolean;
  username?: string;
};

type SessionResponse = {
  user: AuthenticatedUser;
};

type LoginResponse = {
  status: string;
  user: AuthenticatedUser;
};

export function getCurrentUser(signal?: AbortSignal) {
  return apiClient.get<SessionResponse>("/auth/me/", { signal }).then((payload) => payload.user);
}

export function login(credentials: { login: string; password: string }) {
  return apiClient
    .post<LoginResponse>("/auth/login/", { credentials })
    .then((payload) => payload.user);
}

export function logout() {
  return apiClient.post<{ status: string }>("/auth/logout/");
}

export function hasAdminAccess(user: AuthenticatedUser | null) {
  if (user === null) {
    return false;
  }

  return user.role === "superuser" || user.role === "admin" || Boolean(user.superuser || user.admin);
}

export function canEditEntities(user: AuthenticatedUser | null) {
  return user?.role === "superuser" || Boolean(user?.superuser);
}
