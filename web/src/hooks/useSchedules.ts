import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createSchedule,
  deleteSchedule,
  getSchedules,
  runScheduleNow,
  updateSchedule,
} from '../api/endpoints'
import { queryKeys } from '../api/queryKeys'
import type {
  Schedule,
  ScheduleCreatePayload,
  ScheduleUpdatePayload,
} from '../api/types'

interface SchedulesResponse {
  schedules: Schedule[]
}

export function useSchedules() {
  return useQuery({
    queryKey: queryKeys.schedules,
    queryFn: getSchedules,
    retry: 1,
  })
}

export function useCreateSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ScheduleCreatePayload) => createSchedule(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedules })
    },
  })
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string
      payload: ScheduleUpdatePayload
    }) => updateSchedule(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedules })
    },
  })
}

export function useToggleSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSchedule(id, { enabled }),
    onMutate: async ({ id, enabled }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.schedules })
      const previous = queryClient.getQueryData<SchedulesResponse>(
        queryKeys.schedules,
      )
      queryClient.setQueryData<SchedulesResponse>(queryKeys.schedules, (old) =>
        old
          ? {
              schedules: old.schedules.map((schedule) =>
                schedule.id === id ? { ...schedule, enabled } : schedule,
              ),
            }
          : old,
      )
      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.schedules, context.previous)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedules })
    },
  })
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedules })
    },
  })
}

export function useRunScheduleNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => runScheduleNow(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.schedules })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}
