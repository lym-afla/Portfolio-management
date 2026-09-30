// Applied only inside workspace pages while the visual pilot is evaluated.
export const workspaceDefaults = {
  VCard: { elevation: 0, rounded: 'lg', border: true },
  VBtn: { rounded: 'sm', elevation: 0 },
  VTextField: { variant: 'outlined', density: 'compact' },
  VSelect: { variant: 'outlined', density: 'compact' },
  VAutocomplete: { variant: 'outlined', density: 'compact' },
  VDataTable: { density: 'compact' },
} as const
