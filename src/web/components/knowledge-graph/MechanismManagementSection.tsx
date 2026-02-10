'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { MechanismHeader } from '@/components/knowledge-graph/MechanismHeader'
import { MechanismTable } from '@/components/knowledge-graph/MechanismTable'
import { MechanismEditorDialog } from '@/components/knowledge-graph/MechanismEditorDialog'
import { DeleteMechanismDialog } from '@/components/knowledge-graph/DeleteMechanismDialog'
import {
  createMechanismAction,
  deleteMechanismAction,
  updateMechanismAction,
} from '@/app/actions/mechanisms'
import type { PaginatedResponse } from '@/types/generated'
import type {
  Mechanism,
  MechanismCreateRequest,
  MechanismUpdateRequest,
} from '@/types/mechanisms'

interface MechanismManagementSectionProps {
  mechanisms: PaginatedResponse<Mechanism> | null
  spaceId: string
  error?: string | null
  canManage?: boolean
  promotedMechanism?: Mechanism | null
  onPromotionHandled?: () => void
}

export function MechanismManagementSection({
  mechanisms,
  spaceId,
  error,
  canManage = false,
  promotedMechanism = null,
  onPromotionHandled,
}: MechanismManagementSectionProps) {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [activeMechanism, setActiveMechanism] = useState<Mechanism | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Mechanism | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    if (promotedMechanism) {
      setActiveMechanism(promotedMechanism)
      setEditorOpen(true)
      onPromotionHandled?.()
    }
  }, [promotedMechanism, onPromotionHandled])

  const listError =
    error ?? (mechanisms === null ? 'Unable to load mechanisms. Please retry.' : null)

  const filtered = useMemo(() => {
    const mechanismItems = mechanisms?.items ?? []
    if (!search.trim()) {
      return mechanismItems
    }
    const query = search.trim().toLowerCase()
    return mechanismItems.filter(
      (mechanism) =>
        mechanism.name.toLowerCase().includes(query) ||
        (mechanism.description ?? '').toLowerCase().includes(query),
    )
  }, [mechanisms, search])

  const openCreate = () => {
    setActiveMechanism(null)
    setEditorOpen(true)
  }

  const openEdit = (mechanism: Mechanism) => {
    setActiveMechanism(mechanism)
    setEditorOpen(true)
  }

  const refreshList = () => {
    startTransition(() => router.refresh())
  }

  const saveMechanism = async (
    payload: MechanismCreateRequest | MechanismUpdateRequest,
  ) => {
    setIsSaving(true)
    try {
      if (activeMechanism) {
        const result = await updateMechanismAction(spaceId, activeMechanism.id, payload)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Updated ${result.data.name}`)
      } else {
        const result = await createMechanismAction(
          spaceId,
          payload as MechanismCreateRequest,
        )
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Created ${result.data.name}`)
      }
      setEditorOpen(false)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('Failed to save mechanism', err)
      toast.error('Unable to save mechanism')
    } finally {
      setIsSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) {
      return
    }
    setIsDeleting(true)
    try {
      const result = await deleteMechanismAction(spaceId, deleteTarget.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`Deleted ${deleteTarget.name}`)
      setDeleteTarget(null)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('Failed to delete mechanism', err)
      toast.error('Unable to delete mechanism')
    } finally {
      setIsDeleting(false)
    }
  }

  const closeDeleteDialog = (open: boolean) => {
    if (!open) {
      setDeleteTarget(null)
    }
  }

  return (
    <Card>
      <MechanismHeader
        search={search}
        searchChange={setSearch}
        createAction={openCreate}
        refreshAction={refreshList}
        isRefreshing={isPending}
        canCreate={canManage}
      />
      <CardContent>
        <Alert className="mb-4 border-muted bg-muted/30">
          <AlertTitle>Canonical mechanisms only</AlertTitle>
          <AlertDescription>
            Use Statements of Understanding to explore hypotheses. Promote to a mechanism
            only when evidence is well supported and ready for reuse. Draft → Reviewed →
            Canonical captures the lifecycle.
          </AlertDescription>
        </Alert>
        {!canManage && (
          <div className="mb-4 rounded border border-dashed px-4 py-3 text-sm text-muted-foreground">
            You have read-only access. Ask a curator or admin to create or edit mechanisms.
          </div>
        )}
        {listError && (
          <div className="mb-4 rounded border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {listError}
          </div>
        )}

        {filtered.length === 0 ? (
          <div className="flex items-center gap-2 rounded border border-dashed px-4 py-8 text-muted-foreground">
            No mechanisms available.
          </div>
        ) : (
          <MechanismTable
            mechanisms={filtered}
            editAction={openEdit}
            deleteAction={setDeleteTarget}
            canManage={canManage}
          />
        )}
      </CardContent>

      {canManage && (
        <MechanismEditorDialog
          open={editorOpen}
          setOpen={setEditorOpen}
          mechanism={activeMechanism}
          spaceId={spaceId}
          submitAction={saveMechanism}
          isSubmitting={isSaving}
        />
      )}

      {canManage && (
        <DeleteMechanismDialog
          open={Boolean(deleteTarget)}
          setOpen={closeDeleteDialog}
          mechanism={deleteTarget}
          confirmAction={confirmDelete}
          isPending={isDeleting}
        />
      )}
    </Card>
  )
}
