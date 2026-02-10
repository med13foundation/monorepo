'use client'

import { useMemo, useState, useTransition } from 'react'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { StatementHeader } from '@/components/knowledge-graph/StatementHeader'
import { StatementTable } from '@/components/knowledge-graph/StatementTable'
import { StatementEditorDialog } from '@/components/knowledge-graph/StatementEditorDialog'
import { DeleteStatementDialog } from '@/components/knowledge-graph/DeleteStatementDialog'
import {
  createStatementAction,
  deleteStatementAction,
  promoteStatementAction,
  updateStatementAction,
} from '@/app/actions/statements'
import type { PaginatedResponse } from '@/types/generated'
import type { Mechanism } from '@/types/mechanisms'
import type {
  Statement,
  StatementCreateRequest,
  StatementUpdateRequest,
} from '@/types/statements'

interface StatementManagementSectionProps {
  statements: PaginatedResponse<Statement> | null
  spaceId: string
  error?: string | null
  canManage?: boolean
  canPromote?: boolean
  onPromoted?: (mechanism: Mechanism) => void
}

export function StatementManagementSection({
  statements,
  spaceId,
  error,
  canManage = false,
  canPromote = false,
  onPromoted,
}: StatementManagementSectionProps) {
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [activeStatement, setActiveStatement] = useState<Statement | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Statement | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isPromoting, setIsPromoting] = useState(false)
  const [isPending, startTransition] = useTransition()

  const listError =
    error ?? (statements === null ? 'Unable to load statements. Please retry.' : null)

  const filtered = useMemo(() => {
    const statementItems = statements?.items ?? []
    if (!search.trim()) {
      return statementItems
    }
    const query = search.trim().toLowerCase()
    return statementItems.filter(
      (statement) =>
        statement.title.toLowerCase().includes(query) ||
        statement.summary.toLowerCase().includes(query),
    )
  }, [statements, search])

  const openCreate = () => {
    setActiveStatement(null)
    setEditorOpen(true)
  }

  const openEdit = (statement: Statement) => {
    setActiveStatement(statement)
    setEditorOpen(true)
  }

  const refreshList = () => {
    startTransition(() => router.refresh())
  }

  const saveStatement = async (
    payload: StatementCreateRequest | StatementUpdateRequest,
  ) => {
    setIsSaving(true)
    try {
      if (activeStatement) {
        const result = await updateStatementAction(spaceId, activeStatement.id, payload)
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Updated ${result.data.title}`)
      } else {
        const result = await createStatementAction(
          spaceId,
          payload as StatementCreateRequest,
        )
        if (!result.success) {
          toast.error(result.error)
          return
        }
        toast.success(`Created ${result.data.title}`)
      }
      setEditorOpen(false)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('Failed to save statement', err)
      toast.error('Unable to save statement')
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
      const result = await deleteStatementAction(spaceId, deleteTarget.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`Deleted ${deleteTarget.title}`)
      setDeleteTarget(null)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('Failed to delete statement', err)
      toast.error('Unable to delete statement')
    } finally {
      setIsDeleting(false)
    }
  }

  const confirmPromote = async (statement: Statement) => {
    setIsPromoting(true)
    try {
      const result = await promoteStatementAction(spaceId, statement.id)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success(`Promoted ${statement.title} to a mechanism`)
      onPromoted?.(result.data)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('Failed to promote statement', err)
      toast.error('Unable to promote statement')
    } finally {
      setIsPromoting(false)
    }
  }

  const closeDeleteDialog = (open: boolean) => {
    if (!open) {
      setDeleteTarget(null)
    }
  }

  return (
    <Card>
      <StatementHeader
        search={search}
        searchChange={setSearch}
        createAction={openCreate}
        refreshAction={refreshList}
        isRefreshing={isPending}
        canCreate={canManage}
      />
      <CardContent>
        <Alert className="mb-4 border-muted bg-muted/30">
          <AlertTitle>Statements are for thinking</AlertTitle>
          <AlertDescription>
            Capture evolving hypotheses here. Promote to a mechanism only when the statement
            is well supported with moderate or stronger evidence and at least one phenotype.
          </AlertDescription>
        </Alert>
        {!canManage && (
          <div className="mb-4 rounded border border-dashed px-4 py-3 text-sm text-muted-foreground">
            You have read-only access. Ask a researcher or curator to add statements.
          </div>
        )}
        {listError && (
          <div className="mb-4 rounded border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {listError}
          </div>
        )}

        {filtered.length === 0 ? (
          <div className="flex items-center gap-2 rounded border border-dashed px-4 py-8 text-muted-foreground">
            No statements available.
          </div>
        ) : (
          <StatementTable
            statements={filtered}
            editAction={openEdit}
            deleteAction={setDeleteTarget}
            promoteAction={confirmPromote}
            canManage={canManage}
            canPromote={canPromote && !isPromoting}
          />
        )}
      </CardContent>

      {canManage && (
        <StatementEditorDialog
          open={editorOpen}
          setOpen={setEditorOpen}
          statement={activeStatement}
          spaceId={spaceId}
          submitAction={saveStatement}
          isSubmitting={isSaving}
        />
      )}

      {canManage && (
        <DeleteStatementDialog
          open={Boolean(deleteTarget)}
          setOpen={closeDeleteDialog}
          statement={deleteTarget}
          confirmAction={confirmDelete}
          isPending={isDeleting}
        />
      )}
    </Card>
  )
}
