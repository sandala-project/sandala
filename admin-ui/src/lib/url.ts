function hasHttpScheme(value: string) {
  return /^https?:\/\//.test(value);
}

function trimTrailingSlash(value: string) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function ensureLeadingSlash(value: string) {
  return value.startsWith("/") ? value : `/${value}`;
}

function ensureTrailingSlash(value: string) {
  return value.endsWith("/") ? value : `${value}/`;
}

function removeLeadingSlash(value: string) {
  return value.startsWith("/") ? value.slice(1) : value;
}

export function resolveConfiguredUrl(path: string, baseUrl: string) {
  if (baseUrl.length === 0) {
    return path;
  }

  if (hasHttpScheme(baseUrl)) {
    return new URL(removeLeadingSlash(path), ensureTrailingSlash(baseUrl)).toString();
  }

  return `${trimTrailingSlash(baseUrl)}${ensureLeadingSlash(path)}`;
}
