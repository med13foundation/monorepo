"use client"

import type { Control } from 'react-hook-form'

import type { ScheduleFrequency } from '@/types/data-source'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'

import type { ScheduleFormValues } from './DataSourceScheduleDialog'

const frequencyOptions: { label: string; value: ScheduleFrequency }[] = [
  { label: 'Manual', value: 'manual' },
  { label: 'Hourly', value: 'hourly' },
  { label: 'Daily', value: 'daily' },
  { label: 'Weekly', value: 'weekly' },
  { label: 'Monthly', value: 'monthly' },
  { label: 'Cron expression', value: 'cron' },
]

interface DataSourceScheduleFieldsProps {
  control: Control<ScheduleFormValues>
  enabled: boolean
  canEnableSchedule: boolean
  isCron: boolean
}

export function DataSourceScheduleFields({
  control,
  enabled,
  canEnableSchedule,
  isCron,
}: DataSourceScheduleFieldsProps) {
  return (
    <>
      <FormField
        control={control}
        name="enabled"
        render={({ field }) => (
          <FormItem className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <FormLabel>Enable scheduling</FormLabel>
              <FormDescription>
                Configure the schedule details first, then enable automatic ingestion.
              </FormDescription>
            </div>
            <FormControl>
              <Checkbox
                checked={field.value}
                onCheckedChange={field.onChange}
                disabled={!canEnableSchedule}
              />
            </FormControl>
          </FormItem>
        )}
      />
      {!canEnableSchedule && (
        <p className="text-xs text-muted-foreground">
          Complete the schedule details to enable automatic ingestion.
        </p>
      )}
      {enabled && (
        <>
          <FormField
            control={control}
            name="frequency"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Frequency</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select frequency" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {frequencyOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  Choose how often MED13 should attempt ingestion.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={control}
            name="startTime"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Start time</FormLabel>
                <FormControl>
                  <Input type="datetime-local" {...field} />
                </FormControl>
                <FormDescription>
                  Optional. Defaults to immediately running on the next interval.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={control}
            name="timezone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Timezone</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormDescription>
                  Specify the timezone for scheduler calculations.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {isCron && (
            <FormField
              control={control}
              name="cronExpression"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Cron expression</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="0 2 * * *" />
                  </FormControl>
                  <FormDescription>
                    Cron support requires a dedicated scheduler backend; use with caution.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </>
      )}
    </>
  )
}
