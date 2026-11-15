export const queryKeys = {
  health: ['health'] as const,
  appInfo: ['app-info'] as const,
  ai: ['ai-status'] as const,
  providers: ['providers'] as const,
  providerHealth: ['providers', 'health'] as const,
  packs: ['domain-packs'] as const,
  runs: (limit: number) => ['runs', limit] as const,
  run: (runId: string) => ['run', runId] as const,
  analysis: (runId: string) => ['analysis', runId] as const,
  library: ['library'] as const,
  schedules: ['schedules'] as const,
}
