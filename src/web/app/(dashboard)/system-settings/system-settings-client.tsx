"use client"

import { useMemo, useState, useTransition } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle,
  Ban,
  CheckCircle,
  Loader2,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserMinus,
  UserPlus,
} from 'lucide-react'
import { PageHero, StatCard } from '@/components/ui/composition-patterns'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  createUserAction,
  deleteUserAction,
  lockUserAction,
  unlockUserAction,
} from '@/app/actions/users'
import type {
  CreateUserRequest,
  UserListParams,
  UserPublic,
  UserListResponse,
  UserStatisticsResponse,
} from '@/lib/api/users'
import { DataSourceAvailabilitySection } from '@/components/system-settings/DataSourceAvailabilitySection'
import { MaintenanceModePanel } from '@/components/system-settings/MaintenanceModePanel'
import { SpaceSourcePermissionsManager } from '@/components/system-settings/SpaceSourcePermissionsManager'
import { StorageConfigurationManager } from '@/components/system-settings/StorageConfigurationManager'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useRouter } from 'next/navigation'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { ResearchSpace } from '@/types/research-space'

interface SystemSettingsClientProps {
  initialParams: UserListParams
  users: UserListResponse | null
  userStats: UserStatisticsResponse | null
  storageConfigurations: StorageConfigurationListResponse | null
  storageOverview: StorageOverviewResponse | null
  maintenanceState: MaintenanceModeResponse | null
  catalogEntries: SourceCatalogEntry[]
  availabilitySummaries: DataSourceAvailability[]
  spaces: ResearchSpace[]
  currentUserId: string
  isAdmin: boolean
}

const ROLE_FILTERS = [
  { label: 'All roles', value: 'all' },
  { label: 'Administrators', value: 'admin' },
  { label: 'Curators', value: 'curator' },
  { label: 'Researchers', value: 'researcher' },
  { label: 'Viewers', value: 'viewer' },
]

const STATUS_FILTERS = [
  { label: 'All statuses', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Suspended', value: 'suspended' },
  { label: 'Pending verification', value: 'pending_verification' },
  { label: 'Inactive', value: 'inactive' },
]

const roleLabels: Record<UserPublic['role'], string> = {
  admin: 'Administrator',
  curator: 'Curator',
  researcher: 'Researcher',
  viewer: 'Viewer',
}

const statusLabels: Record<UserPublic['status'], string> = {
  active: 'Active',
  inactive: 'Inactive',
  suspended: 'Suspended',
  pending_verification: 'Pending Verification',
}

const statusVariantMap: Record<UserPublic['status'], 'default' | 'secondary' | 'destructive' | 'outline'> = {
  active: 'default',
  inactive: 'secondary',
  suspended: 'destructive',
  pending_verification: 'outline',
}

const initialCreateForm: CreateUserRequest = {
  email: '',
  username: '',
  full_name: '',
  password: '',
  role: 'researcher',
}

export default function SystemSettingsClient({
  initialParams,
  users,
  userStats,
  storageConfigurations,
  storageOverview,
  maintenanceState,
  catalogEntries,
  availabilitySummaries,
  spaces,
  currentUserId,
  isAdmin,
}: SystemSettingsClientProps) {
  const router = useRouter()
  const [filters, setFilters] = useState<UserListParams>(initialParams)
  const [search, setSearch] = useState('')
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<UserPublic | null>(null)
  const [pendingUserId, setPendingUserId] = useState<string | null>(null)
  const [isRefreshing, startRefresh] = useTransition()
  const [isCreatingUser, setIsCreatingUser] = useState(false)
  const [isDeletingUser, setIsDeletingUser] = useState(false)

  const listData: UserListResponse = users ?? {
    users: [],
    total: 0,
    skip: 0,
    limit: 0,
  }
  const statsLoading = userStats === null
  const userListError = users === null ? 'Unable to load user inventory. Please retry.' : null

  const filteredUsers = useMemo(() => {
    let filtered = listData.users
    if (filters.role) {
      filtered = filtered.filter((user) => user.role === filters.role)
    }
    if (filters.status_filter) {
      filtered = filtered.filter((user) => user.status === filters.status_filter)
    }
    if (!search.trim()) {
      return filtered
    }
    const query = search.trim().toLowerCase()
    return filtered.filter(
      (user) =>
        user.full_name.toLowerCase().includes(query) ||
        user.email.toLowerCase().includes(query) ||
        user.username.toLowerCase().includes(query),
    )
  }, [filters.role, filters.status_filter, listData.users, search])

  if (!isAdmin) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="size-5 text-destructive" />
            Restricted Area
          </CardTitle>
          <CardDescription>
            System Settings are only available to MED13 administrators.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const handleRoleChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      role: value === 'all' ? undefined : value,
      skip: 0,
    }))
  }

  const handleStatusChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      status_filter: value === 'all' ? undefined : value,
      skip: 0,
    }))
  }

  const handleCreateUser = async (payload: CreateUserRequest) => {
    try {
      setIsCreatingUser(true)
      const result = await createUserAction(payload)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`User ${payload.full_name || payload.email} created`)
      setIsCreateOpen(false)
      router.refresh()
    } catch (error) {
      console.error('Failed to create user', error)
      toast.error('Failed to create user')
    } finally {
      setIsCreatingUser(false)
    }
  }

  const handleToggleSuspension = async (user: UserPublic) => {
    setPendingUserId(user.id)
    try {
      if (user.status === 'suspended') {
        const result = await unlockUserAction(user.id)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Reactivated ${user.full_name}`)
      } else {
        const result = await lockUserAction(user.id)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Suspended ${user.full_name}`)
      }
      router.refresh()
    } catch (error) {
      console.error('Failed to update user status', error)
      toast.error('Unable to update user status')
    } finally {
      setPendingUserId(null)
    }
  }

  const handleDeleteUser = async () => {
    if (!deleteTarget) {
      return
    }
    setPendingUserId(deleteTarget.id)
    try {
      setIsDeletingUser(true)
      const result = await deleteUserAction(deleteTarget.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`Removed ${deleteTarget.full_name}`)
      setDeleteTarget(null)
      router.refresh()
    } catch (error) {
      console.error('Failed to delete user', error)
      toast.error('Unable to delete user')
    } finally {
      setPendingUserId(null)
      setIsDeletingUser(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHero
        title="System Settings"
        description="Centralized controls for MED13 administrators. Manage global access, enforce security policy, and oversee user lifecycle events."
        variant="default"
        actions={
          <Button onClick={() => setIsCreateOpen(true)}>
            <UserPlus className="mr-2 size-4" />
            New User
          </Button>
        }
      />

      <Tabs defaultValue="users" className="space-y-6">
        <TabsList>
          <TabsTrigger value="users">User Management</TabsTrigger>
          <TabsTrigger value="permissions">Source Permissions</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="maintenance">Maintenance</TabsTrigger>
        </TabsList>
        <TabsContent value="users" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Total Users"
              value={userStats?.total_users?.toLocaleString() ?? 0}
              description="Across all roles"
              icon={<Shield className="size-4 text-muted-foreground" />}
              isLoading={statsLoading}
            />
            <StatCard
              title="Active"
              value={userStats?.active_users ?? 0}
              description="Currently enabled accounts"
              icon={<CheckCircle className="size-4 text-emerald-500" />}
              isLoading={statsLoading}
            />
            <StatCard
              title="Suspended"
              value={userStats?.suspended_users ?? 0}
              description="Locked for review"
              icon={<Ban className="size-4 text-amber-500" />}
              isLoading={statsLoading}
            />
            <StatCard
              title="Pending Verification"
              value={userStats?.pending_verification ?? 0}
              description="Awaiting onboarding"
              icon={<AlertTriangle className="size-4 text-blue-500" />}
              isLoading={statsLoading}
            />
          </div>

          <Card>
        <CardHeader className="space-y-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="font-heading text-xl">User Directory</CardTitle>
              <CardDescription>
                Provision, suspend, or retire MED13 accounts globally.
              </CardDescription>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button
                variant="outline"
                onClick={() => startRefresh(() => router.refresh())}
                disabled={isRefreshing}
              >
                {isRefreshing ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Refreshing…
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 size-4" />
                    Refresh
                  </>
                )}
              </Button>
              <Button onClick={() => setIsCreateOpen(true)}>
                <UserPlus className="mr-2 size-4" />
                Add User
              </Button>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="role-filter">Role</Label>
              <Select
                value={filters.role ?? 'all'}
                onValueChange={handleRoleChange}
              >
                <SelectTrigger id="role-filter">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_FILTERS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="status-filter">Status</Label>
              <Select
                value={filters.status_filter ?? 'all'}
                onValueChange={handleStatusChange}
              >
                <SelectTrigger id="status-filter">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTERS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="search">Search</Label>
              <Input
                id="search"
                placeholder="Search by name or email"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {userListError && (
            <div className="mb-4 flex items-center gap-2 rounded border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              <ShieldAlert className="size-4" />
              {userListError}
            </div>
          )}

          {filteredUsers.length === 0 ? (
            <div className="flex items-center gap-2 rounded border border-dashed px-4 py-10 text-muted-foreground">
              <UserMinus className="size-5" />
              No users matched the current filters.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Last Login</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUsers.map((user) => (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="font-medium">{user.full_name}</span>
                          <span className="text-xs text-muted-foreground">
                            {user.email}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{roleLabels[user.role]}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariantMap[user.status]}>
                          {statusLabels[user.status]}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatDate(user.created_at)}</TableCell>
                      <TableCell>{formatDate(user.last_login)}</TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleToggleSuspension(user)}
                            disabled={
                              user.id === currentUserId ||
                              pendingUserId === user.id
                            }
                          >
                            {pendingUserId === user.id ? (
                              <Loader2 className="mr-2 size-4 animate-spin" />
                            ) : user.status === 'suspended' ? (
                              <CheckCircle className="mr-2 size-4 text-emerald-500" />
                            ) : (
                              <Ban className="mr-2 size-4 text-amber-500" />
                            )}
                            {user.status === 'suspended' ? 'Activate' : 'Suspend'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => setDeleteTarget(user)}
                            disabled={
                              user.id === currentUserId ||
                              pendingUserId === user.id ||
                              isDeletingUser
                            }
                          >
                            <Trash2 className="mr-2 size-4" />
                            Remove
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="mt-3 text-sm text-muted-foreground">
                Showing {filteredUsers.length} of {listData.total ?? filteredUsers.length} users
              </p>
            </div>
          )}
        </CardContent>
      </Card>
      <RoleDistributionCard isLoading={statsLoading} roles={userStats?.by_role ?? {}} />

      <CreateUserDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        onSubmit={handleCreateUser}
        isSubmitting={isCreatingUser}
      />

      <DeleteUserDialog
        user={deleteTarget}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDeleteUser}
        isPending={isDeletingUser && pendingUserId === deleteTarget?.id}
      />
    </TabsContent>
    <TabsContent value="permissions" className="space-y-6">
      <DataSourceAvailabilitySection
        catalogEntries={catalogEntries}
        availabilitySummaries={availabilitySummaries}
        spaces={spaces}
      />
      <SpaceSourcePermissionsManager
        catalogEntries={catalogEntries}
        availabilitySummaries={availabilitySummaries}
        spaces={spaces}
      />
    </TabsContent>
    <TabsContent value="storage" className="space-y-6">
      <StorageConfigurationManager
        configurations={storageConfigurations}
        overview={storageOverview}
        maintenanceState={maintenanceState}
      />
    </TabsContent>
    <TabsContent value="maintenance" className="space-y-6">
      <MaintenanceModePanel maintenanceState={maintenanceState} />
    </TabsContent>
  </Tabs>
    </div>
  )
}

function RoleDistributionCard({
  roles,
  isLoading,
}: {
  roles: Record<string, number>
  isLoading: boolean
}) {
  const total = Object.values(roles).reduce((sum, value) => sum + value, 0)
  const entries = Object.entries(roles).sort((a, b) => b[1] - a[1])
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading">Role Distribution</CardTitle>
        <CardDescription>Snapshot of platform access levels.</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-3 py-6 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
            Loading distribution…
          </div>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No role data available.</p>
        ) : (
          <div className="space-y-3">
            {entries.map(([role, count]) => (
              <div key={role} className="flex items-center gap-3">
                <div className="flex-1">
                  <p className="text-sm font-medium capitalize">{role}</p>
                  <p className="text-xs text-muted-foreground">
                    {(total > 0 ? Math.round((count / total) * 100) : 0).toFixed(0)}% of users
                  </p>
                </div>
                <Badge variant="outline">{count}</Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CreateUserDialog({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: CreateUserRequest) => Promise<void>
  isSubmitting: boolean
}) {
  const [form, setForm] = useState<CreateUserRequest>(initialCreateForm)

  const updateField = (field: keyof CreateUserRequest, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async () => {
    await onSubmit(form)
    setForm(initialCreateForm)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setForm(initialCreateForm)
        }
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create administrator-managed account</DialogTitle>
          <DialogDescription>
            Provision a new MED13 user. Credentials are issued immediately and bypass email verification.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="full_name">Full name</Label>
              <Input
                id="full_name"
                value={form.full_name}
                onChange={(event) => updateField('full_name', event.target.value)}
                placeholder="Dr. Jane Smith"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={form.email}
                onChange={(event) => updateField('email', event.target.value)}
                placeholder="user@med13.org"
              />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={form.username}
                onChange={(event) => updateField('username', event.target.value)}
                placeholder="med13_user"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Role</Label>
              <Select
                value={form.role}
                onValueChange={(value) => updateField('role', value)}
              >
                <SelectTrigger id="role">
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_FILTERS.filter((role) => role.value !== 'all').map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Temporary password</Label>
            <Input
              id="password"
              type="password"
              value={form.password}
              onChange={(event) => updateField('password', event.target.value)}
              placeholder="Strong passphrase"
            />
            <p className="text-xs text-muted-foreground">
              Password must meet MED13 security requirements. Share via secure channel only.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Creating…
              </>
            ) : (
              <>
                <ShieldCheck className="mr-2 size-4" />
                Create User
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteUserDialog({
  user,
  onCancel,
  onConfirm,
  isPending,
}: {
  user: UserPublic | null
  onCancel: () => void
  onConfirm: () => Promise<void> | void
  isPending: boolean
}) {
  return (
    <Dialog open={Boolean(user)} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove user access</DialogTitle>
          <DialogDescription>
            This permanently deletes the account and associated authentication credentials.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm">
            {user ? (
              <>
                Are you sure you want to delete <strong>{user.full_name}</strong> ({user.email})?
              </>
            ) : (
              'Select a user to remove.'
            )}
          </p>
          <p className="text-xs text-muted-foreground">
            This action is irreversible and should comply with MED13 access governance policies.
          </p>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => onConfirm()}
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Removing…
              </>
            ) : (
              <>
                <Trash2 className="mr-2 size-4" />
                Remove User
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function formatDate(value: string | null) {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
