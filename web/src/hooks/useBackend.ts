import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getAIStatus,
  getAppInfo,
  getDomainPacks,
  getHealth,
  getProviders,
} from '../api/endpoints'
import { queryKeys } from '../api/queryKeys'

const metaOptions = {
  retry: 0,
  staleTime: 30_000,
  refetchOnWindowFocus: false,
} as const

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    ...metaOptions,
  })
}

export function useAppInfo() {
  return useQuery({
    queryKey: queryKeys.appInfo,
    queryFn: getAppInfo,
    ...metaOptions,
  })
}

export function useAIStatus() {
  return useQuery({
    queryKey: queryKeys.ai,
    queryFn: getAIStatus,
    ...metaOptions,
  })
}

export function useProviders() {
  return useQuery({
    queryKey: queryKeys.providers,
    queryFn: getProviders,
    ...metaOptions,
  })
}

export function useDomainPacks() {
  return useQuery({
    queryKey: queryKeys.packs,
    queryFn: getDomainPacks,
    ...metaOptions,
  })
}

export function useBackend() {
  const queryClient = useQueryClient()
  const health = useHealth()
  const providers = useProviders()
  const packs = useDomainPacks()
  const ai = useAIStatus()
  const appInfo = useAppInfo()

  const online = health.isSuccess
  const loading = health.isLoading

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.health })
    void queryClient.invalidateQueries({ queryKey: queryKeys.providers })
    void queryClient.invalidateQueries({ queryKey: queryKeys.packs })
    void queryClient.invalidateQueries({ queryKey: queryKeys.ai })
    void queryClient.invalidateQueries({ queryKey: queryKeys.appInfo })
  }

  return {
    health,
    providers,
    packs,
    ai,
    appInfo,
    online,
    loading,
    refresh,
  }
}
