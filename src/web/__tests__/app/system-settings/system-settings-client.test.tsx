import type { ComponentProps } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SystemSettingsClient from '@/app/(dashboard)/system-settings/system-settings-client'
import type {
  UserListParams,
  UserListResponse,
  UserStatisticsResponse,
} from '@/lib/api/users'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { ResearchSpace } from '@/types/research-space'

const mockCreateUserAction = jest.fn()
const mockLockUserAction = jest.fn()
const mockUnlockUserAction = jest.fn()
const mockDeleteUserAction = jest.fn()

jest.mock('@/app/actions/users', () => ({
  createUserAction: (...args: unknown[]) => mockCreateUserAction(...args),
  lockUserAction: (...args: unknown[]) => mockLockUserAction(...args),
  unlockUserAction: (...args: unknown[]) => mockUnlockUserAction(...args),
  deleteUserAction: (...args: unknown[]) => mockDeleteUserAction(...args),
}))

jest.mock('@/components/system-settings/DataSourceAvailabilitySection', () => ({
  DataSourceAvailabilitySection: () => <div data-testid="data-source-availability-section" />,
}))

jest.mock('@/components/system-settings/StorageConfigurationManager', () => ({
  StorageConfigurationManager: () => <div data-testid="storage-configuration-manager" />,
}))

jest.mock('@/components/system-settings/MaintenanceModePanel', () => ({
  MaintenanceModePanel: () => <div data-testid="maintenance-mode-panel" />,
}))

jest.mock('@/components/system-settings/SpaceSourcePermissionsManager', () => ({
  SpaceSourcePermissionsManager: () => <div data-testid="space-source-permissions-manager" />,
}))
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

type SystemSettingsProps = ComponentProps<typeof SystemSettingsClient>

const initialParams: UserListParams = { skip: 0, limit: 25 }

const baseUsers: UserListResponse = {
  users: [],
  total: 0,
  skip: 0,
  limit: 25,
}

const baseUserStats: UserStatisticsResponse = {
  total_users: 0,
  active_users: 0,
  inactive_users: 0,
  suspended_users: 0,
  pending_verification: 0,
  by_role: {},
  recent_registrations: 0,
  recent_logins: 0,
}

const baseStorageConfigurations: StorageConfigurationListResponse | null = null
const baseStorageOverview: StorageOverviewResponse | null = null
const baseMaintenanceState: MaintenanceModeResponse | null = null
const baseCatalogEntries: SourceCatalogEntry[] = []
const baseAvailabilitySummaries: DataSourceAvailability[] = []
const baseSpaces: ResearchSpace[] = []
const baseProps: SystemSettingsProps = {
  initialParams,
  users: baseUsers,
  userStats: baseUserStats,
  storageConfigurations: baseStorageConfigurations,
  storageOverview: baseStorageOverview,
  maintenanceState: baseMaintenanceState,
  catalogEntries: baseCatalogEntries,
  availabilitySummaries: baseAvailabilitySummaries,
  spaces: baseSpaces,
  currentUserId: 'admin-1',
  isAdmin: true,
}

const renderClient = (overrides: Partial<SystemSettingsProps> = {}) => {
  return render(<SystemSettingsClient {...baseProps} {...overrides} />)
}

describe('SystemSettingsClient', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateUserAction.mockResolvedValue({
      success: true,
      data: {
        user: {
          id: 'new-user',
          email: 'new@med13.org',
          username: 'new-user',
          full_name: 'New User',
          role: 'researcher',
          status: 'active',
          email_verified: true,
          last_login: null,
          created_at: new Date().toISOString(),
        },
      },
    })
    mockLockUserAction.mockResolvedValue({ success: true, data: { message: 'ok' } })
    mockUnlockUserAction.mockResolvedValue({ success: true, data: { message: 'ok' } })
    mockDeleteUserAction.mockResolvedValue({ success: true, data: { message: 'ok' } })
  })

  it('shows restricted message for non-admin users', () => {
    renderClient({ isAdmin: false })

    expect(screen.getByText(/Restricted Area/i)).toBeInTheDocument()
  })

  it('renders table data and triggers suspend action', async () => {
    const user = userEvent.setup()
    renderClient({
      users: {
        users: [
          {
            id: 'user-1',
            email: 'researcher@med13.org',
            username: 'researcher1',
            full_name: 'Researcher One',
            role: 'researcher',
            status: 'active',
            email_verified: true,
            last_login: '2024-01-01T00:00:00.000Z',
            created_at: '2023-01-01T00:00:00.000Z',
          },
        ],
        total: 1,
        skip: 0,
        limit: 25,
      },
      currentUserId: 'admin-1',
    })

    expect(screen.getByText('Researcher One')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Suspend/i }))

    await waitFor(() => {
      expect(mockLockUserAction).toHaveBeenCalledWith('user-1')
    })
  })

  it('creates a user from the dialog form', async () => {
    const user = userEvent.setup()
    renderClient()

    await user.click(screen.getByRole('button', { name: /New User/i }))
    await user.type(screen.getByLabelText(/Full name/i), 'Dr. Jane Doe')
    await user.type(screen.getByLabelText(/^Email/i), 'jane@med13.org')
    await user.type(screen.getByLabelText(/Username/i), 'jane')
    await user.type(screen.getByLabelText(/Temporary password/i), 'Password!234')

    await user.click(screen.getByRole('button', { name: /Create User/i }))

    await waitFor(() => {
      expect(mockCreateUserAction).toHaveBeenCalledWith({
        email: 'jane@med13.org',
        username: 'jane',
        full_name: 'Dr. Jane Doe',
        password: 'Password!234',
        role: 'researcher',
      })
    })
  })
})
