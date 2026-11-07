export const STRUCTURE_QUERY_OPTIONS = {
  gcTime: Infinity,
  staleTime: Infinity,
};

export const SCHEMA_QUERY_OPTIONS = {
  ...STRUCTURE_QUERY_OPTIONS,
  structuralSharing: false,
};

export const EPHEMERAL_NODE_QUERY_OPTIONS = {
  gcTime: 0,
  refetchOnMount: "always" as const,
  staleTime: 0,
};
