import type { InjectionKey } from 'vue'

// Workspace pages own their visible heading; the shell releases its duplicate.
export const workspaceHeadingKey: InjectionKey<() => () => void> = Symbol('workspace-heading')
