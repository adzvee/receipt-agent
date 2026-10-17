import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'
import { switchUser } from './auth'

/** The app's data cache. If any request says "not logged in" (e.g. the session expired),
 *  the app goes back to the login page. */
export function createQueryClient(options: { retry?: boolean } = {}): QueryClient {
  const onError = (error: Error) => {
    if (error instanceof ApiError && error.status === 401) switchUser(queryClient, null)
  }
  const queryClient: QueryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, ...options } },
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
  })
  return queryClient
}
