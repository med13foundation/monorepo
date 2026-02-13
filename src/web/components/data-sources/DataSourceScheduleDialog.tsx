"use client"

import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { Loader2 } from 'lucide-react'

import { configureDataSourceScheduleAction, updateDataSourceAction } from '@/app/actions/data-sources'
import type { DataSource } from '@/types/data-source'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Form } from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'

import { DataSourceScheduleFields } from './DataSourceScheduleFields'

const scheduleSchema = z.object({
  enabled: z.boolean().default(false),
  frequency: z.enum(['manual', 'hourly', 'daily', 'weekly', 'monthly', 'cron']),
  startTime: z.string().optional(),
  timezone: z.string().min(1, 'Timezone is required'),
  cronExpression: z.string().optional(),
})

export type ScheduleFormValues = z.infer<typeof scheduleSchema>

interface DataSourceScheduleDialogProps {
  source: DataSource | null
  spaceId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function toLocalDatetimeInput(value?: string | null): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

export function DataSourceScheduleDialog({
  source,
  spaceId,
  open,
  onOpenChange,
}: DataSourceScheduleDialogProps) {
  const router = useRouter()
  const [isSavingSchedule, setIsSavingSchedule] = useState(false)
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false)
  const schedule = source?.ingestion_schedule

  const defaultValues = useMemo<ScheduleFormValues>(
    () => ({
      enabled: schedule?.enabled ?? false,
      frequency: schedule?.frequency ?? 'manual',
      startTime: toLocalDatetimeInput(schedule?.start_time),
      timezone: schedule?.timezone ?? 'UTC',
      cronExpression: schedule?.cron_expression ?? '',
    }),
    [schedule],
  )

  const form = useForm<ScheduleFormValues>({
    resolver: zodResolver(scheduleSchema),
    defaultValues,
  })

  useEffect(() => {
    form.reset(defaultValues)
  }, [defaultValues, form, open])

  if (!source) {
    return null
  }

  const onSubmit = async (values: ScheduleFormValues) => {
    const payload = {
      enabled: values.enabled,
      frequency: values.frequency,
      timezone: values.timezone,
      start_time: values.startTime ? new Date(values.startTime).toISOString() : null,
      cron_expression:
        values.frequency === 'cron' ? values.cronExpression?.trim() || null : null,
    }

    try {
      setIsSavingSchedule(true)
      const result = await configureDataSourceScheduleAction(source.id, payload, spaceId)
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success('Schedule updated')
      onOpenChange(false)
      router.refresh()
    } catch (error) {
      console.error('Failed to update schedule', error)
      toast.error('Failed to update schedule')
    } finally {
      setIsSavingSchedule(false)
    }
  }

  const enabled = form.watch('enabled')
  const frequency = form.watch('frequency')
  const timezone = form.watch('timezone')
  const cronExpression = form.watch('cronExpression')
  const isCron = frequency === 'cron'
  const hasScheduleBasics =
    typeof timezone === 'string' &&
    timezone.trim().length > 0 &&
    (!isCron || (cronExpression ?? '').trim().length > 0)
  const canEnableSchedule = hasScheduleBasics
  const statusToggleDisabled =
    isUpdatingStatus || source.status === 'archived' || !hasScheduleBasics
  const statusLabel = source.status === 'active' ? 'Enabled' : 'Disabled'

  const handleStatusToggle = async (enabled: boolean) => {
    try {
      setIsUpdatingStatus(true)
      const result = await updateDataSourceAction(
        source.id,
        { status: enabled ? 'active' : 'inactive' },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      router.refresh()
    } catch (error) {
      // Error toast is handled by the mutation
    } finally {
      setIsUpdatingStatus(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Configure ingestion schedule</DialogTitle>
          <DialogDescription>
            Control how often MED13 automatically ingests data from this source.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <DataSourceScheduleFields
              control={form.control}
              enabled={enabled}
              canEnableSchedule={canEnableSchedule}
              isCron={isCron}
            />

            <div className="rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="source-status-toggle">Source status</Label>
                  <p className="text-sm text-muted-foreground">
                    Enable the source after all configuration is complete.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{statusLabel}</span>
                  <Switch
                    id="source-status-toggle"
                    checked={source.status === 'active'}
                    onCheckedChange={handleStatusToggle}
                    disabled={statusToggleDisabled}
                  />
                </div>
              </div>
              {statusToggleDisabled && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Complete configuration before enabling this source.
                </p>
              )}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSavingSchedule}>
                {isSavingSchedule && (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                )}
                Save schedule
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
