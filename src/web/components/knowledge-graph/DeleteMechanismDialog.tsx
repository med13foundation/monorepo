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
import type { Mechanism } from '@/types/mechanisms'

interface DeleteMechanismDialogProps {
  open: boolean
  setOpen: (open: boolean) => void
  mechanism: Mechanism | null
  confirmAction: () => void
  isPending: boolean
}

export function DeleteMechanismDialog({
  open,
  setOpen,
  mechanism,
  confirmAction,
  isPending,
}: DeleteMechanismDialogProps) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete mechanism</DialogTitle>
          <DialogDescription>
            {mechanism
              ? `Are you sure you want to delete ${mechanism.name}? This action cannot be undone.`
              : 'Select a mechanism to delete.'}
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
