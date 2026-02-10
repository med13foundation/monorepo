'use client'

import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Statement } from '@/types/statements'

interface DeleteStatementDialogProps {
  open: boolean
  setOpen: (open: boolean) => void
  statement: Statement | null
  confirmAction: () => void
  isPending: boolean
}

export function DeleteStatementDialog({
  open,
  setOpen,
  statement,
  confirmAction,
  isPending,
}: DeleteStatementDialogProps) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete statement</DialogTitle>
          <DialogDescription>
            {statement
              ? `Are you sure you want to delete ${statement.title}? This action cannot be undone.`
              : 'Select a statement to delete.'}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={confirmAction} disabled={isPending}>
            {isPending ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Deleting…
              </>
            ) : (
              'Delete'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
