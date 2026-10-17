import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { getMe, type User } from './api'

export const ME_KEY = ['me']

/** The logged-in user (null when logged out), shared by every component. */
export function useCurrentUser() {
  return useQuery({ queryKey: ME_KEY, queryFn: getMe, staleTime: Infinity })
}

/** After logging in or out: set the new user and drop data cached for the previous one. */
export function useSetCurrentUser() {
  const queryClient = useQueryClient()
  return (user: User | null) => switchUser(queryClient, user)
}

export function switchUser(queryClient: QueryClient, user: User | null) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
  queryClient.setQueryData(ME_KEY, user)
}
