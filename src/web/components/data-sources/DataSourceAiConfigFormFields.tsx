import type { UseFormReturn } from 'react-hook-form'

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

import type { AiConfigFormValues } from './DataSourceAiConfigDialog'
import { AiModelSelector } from './AiModelSelector'

interface AiManagedConfigFieldsProps {
  form: UseFormReturn<AiConfigFormValues>
}

interface PubMedConfigFieldsProps {
  form: UseFormReturn<AiConfigFormValues>
}

export function AiManagedConfigFields({ form }: AiManagedConfigFieldsProps) {
  return (
    <>
      <FormField
        control={form.control}
        name="model_id"
        render={({ field }) => (
          <FormItem>
            <FormLabel>AI Model</FormLabel>
            <FormControl>
              <AiModelSelector value={field.value} onChange={field.onChange} />
            </FormControl>
            <FormDescription>
              Choose which AI model powers query generation for this source.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="use_research_space_context"
        render={({ field }) => (
          <FormItem className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <FormLabel>Use research space context</FormLabel>
              <FormDescription>
                Provide the research space description to the agent.
              </FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="agent_prompt"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Agent instructions</FormLabel>
            <FormControl>
              <Textarea
                placeholder="e.g. Focus on clinical case studies and mechanistic pathways."
                className="min-h-[100px]"
                {...field}
              />
            </FormControl>
            <FormDescription>
              Custom instructions to steer the agent behavior.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  )
}

export function PubMedConfigFields({ form }: PubMedConfigFieldsProps) {
  return (
    <>
      <FormField
        control={form.control}
        name="query"
        render={({ field }) => (
          <FormItem>
            <FormLabel>PubMed query</FormLabel>
            <FormControl>
              <Textarea
                {...field}
                className="min-h-[90px] font-mono text-xs"
                placeholder='e.g. "MED13"[Title/Abstract] AND "mediator complex"[Title/Abstract]'
              />
            </FormControl>
            <FormDescription>
              The exact query used for ingestion. AI can refine this when AI-managed mode is enabled.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="max_results"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Per-run paper cap (`max_results`)</FormLabel>
            <FormControl>
              <Input
                type="number"
                min={1}
                max={10000}
                value={field.value}
                onChange={(event) =>
                  field.onChange(
                    Number.isFinite(Number(event.target.value))
                      ? Number(event.target.value)
                      : 1,
                  )
                }
              />
            </FormControl>
            <FormDescription>
              Safety cap to avoid overload during each PubMed run.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="open_access_only"
        render={() => (
          <FormItem className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <FormLabel>Open access only</FormLabel>
              <FormDescription>
                Locked on for PubMed sources so full text can be fetched legally.
              </FormDescription>
            </div>
            <div className="text-xs font-medium text-muted-foreground">ENFORCED</div>
          </FormItem>
        )}
      />
    </>
  )
}
