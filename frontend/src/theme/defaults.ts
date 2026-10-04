// Applied app-wide since the D5 route rollout (Vuetify config in main.js);
// WorkspacePage keeps its scoped provider, which is now redundant but harmless.
export const workspaceDefaults = {
  VCard: { elevation: 0, rounded: 'lg', border: true },
  VBtn: { rounded: 'sm', elevation: 0 },
  VTextField: { variant: 'outlined', density: 'compact' },
  VSelect: { variant: 'outlined', density: 'compact' },
  VAutocomplete: { variant: 'outlined', density: 'compact' },
  VDataTable: { density: 'compact' },
} as const
