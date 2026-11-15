import { createBrowserRouter } from 'react-router-dom'
import { HistoryPage } from '../features/history/HistoryPage'
import { LibraryPage } from '../features/library/LibraryPage'
import { NewRunPage } from '../features/new/NewRunPage'
import { PipelinePage } from '../features/pipeline/PipelinePage'
import { ResultsIndexPage } from '../features/results/ResultsIndexPage'
import { ResultsPage } from '../features/results/ResultsPage'
import { SchedulesPage } from '../features/schedules/SchedulesPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { AppShell } from './AppShell'
import { NotFound } from './NotFound'
import { RouteError } from './RouteError'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <NewRunPage /> },
      { path: 'results', element: <ResultsIndexPage /> },
      { path: 'results/:runId', element: <ResultsPage /> },
      { path: 'pipeline', element: <PipelinePage /> },
      { path: 'schedules', element: <SchedulesPage /> },
      { path: 'history', element: <HistoryPage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
