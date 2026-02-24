"use client"

import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { Loader2 } from 'lucide-react'

import { updateDataSourceAction } from '@/app/actions/data-sources'
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
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
} from '@/components/ui/form'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'
import {
  AiManagedConfigFields,
  PubMedConfigFields,
} from './DataSourceAiConfigFormFields'
import {
  DEFAULT_CLINVAR_AGENT_PROMPT,
  getSourceAgentConfigSnapshot,
} from './sourceAgentConfig'

const aiConfigSchema = z.object({
  is_ai_managed: z.boolean().default(false),
  use_research_space_context: z.boolean().default(true),
  agent_prompt: z.string().default(''),
  model_id: z.string().nullable().default(null),
  query: z.string().default(''),
  max_results: z.number().int().min(1).max(10000).default(100),
  open_access_only: z.boolean().default(true),
})

export type AiConfigFormValues = z.infer<typeof aiConfigSchema>

interface DataSourceAiConfigDialogProps {
  source: DataSource | null
  spaceId?: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DataSourceAiConfigDialog({
  source,
  spaceId,
  open,
  onOpenChange,
}: DataSourceAiConfigDialogProps) {
  const router = useRouter()
  const [isSaving, setIsSaving] = useState(false)

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)
  const config = isRecord(source?.config) ? source?.config : {}
  const metadata = isRecord(config.metadata) ? config.metadata : {}
  const agentConfig = isRecord(metadata.agent_config) ? metadata.agent_config : {}
  const sourceAgentConfigSnapshot = source
    ? getSourceAgentConfigSnapshot(source)
    : null
  const isPubMedSource = source?.source_type === 'pubmed'
  const queryAgentSourceType = sourceAgentConfigSnapshot?.queryAgentSourceType ?? null
  const supportsAiConfiguration = sourceAgentConfigSnapshot?.supportsAiControls ?? false
  const defaultIsAiManaged =
    agentConfig.is_ai_managed === true ||
    sourceAgentConfigSnapshot?.isClinvarCatalogSource === true
  const defaultAgentPrompt =
    typeof agentConfig.agent_prompt === 'string'
      ? agentConfig.agent_prompt
      : sourceAgentConfigSnapshot?.isClinvarCatalogSource
        ? DEFAULT_CLINVAR_AGENT_PROMPT
        : ''
  const defaultUseContext =
    typeof agentConfig.use_research_space_context === 'boolean'
      ? agentConfig.use_research_space_context
      : true
  const defaultModelIdFromConfig =
    typeof agentConfig.model_id === 'string' ? agentConfig.model_id : null
  const defaultQuery =
    typeof metadata.query === 'string'
      ? metadata.query
      : typeof config.query === 'string'
        ? config.query
        : ''
  const defaultMaxResults =
    typeof metadata.max_results === 'number' && Number.isFinite(metadata.max_results)
      ? Math.max(1, Math.min(10000, Math.floor(metadata.max_results)))
      : 100
  const defaultOpenAccessOnly = metadata.open_access_only !== false

  const defaultValues = useMemo<AiConfigFormValues>(
    () => ({
      is_ai_managed: defaultIsAiManaged,
      use_research_space_context: defaultUseContext,
      agent_prompt: defaultAgentPrompt,
      model_id: defaultModelIdFromConfig,
      query: defaultQuery,
      max_results: defaultMaxResults,
      open_access_only: defaultOpenAccessOnly,
    }),
    [
      defaultAgentPrompt,
      defaultIsAiManaged,
      defaultMaxResults,
      defaultModelIdFromConfig,
      defaultOpenAccessOnly,
      defaultQuery,
      defaultUseContext,
    ],
  )

  const form = useForm<AiConfigFormValues>({
    resolver: zodResolver(aiConfigSchema),
    defaultValues,
  })

  useEffect(() => {
    form.reset(defaultValues)
  }, [defaultValues, form, open])

  if (!source || !supportsAiConfiguration) {
    return null
  }

  const onSubmit = async (values: AiConfigFormValues) => {
    const updatedAgentConfig: Record<string, unknown> = {
      ...agentConfig,
      is_ai_managed: values.is_ai_managed,
      agent_prompt: values.agent_prompt,
      use_research_space_context: values.use_research_space_context,
      model_id: values.model_id,
    }
    if (queryAgentSourceType !== null) {
      updatedAgentConfig.query_agent_source_type = queryAgentSourceType
    }
    const updatedMetadata: Record<string, unknown> = {
      ...metadata,
      agent_config: updatedAgentConfig,
    }
    if (isPubMedSource) {
      const normalizedQuery = values.query.trim()
      if (normalizedQuery.length > 0) {
        updatedMetadata.query = normalizedQuery
      }
      updatedMetadata.max_results = Math.max(1, Math.min(10000, values.max_results))
      updatedMetadata.open_access_only = true
    }
    const updatedConfig: Record<string, unknown> = {
      ...config,
      metadata: updatedMetadata,
    }
    if (isPubMedSource) {
      updatedConfig.query = updatedMetadata.query
    }

    try {
      setIsSaving(true)
      const result = await updateDataSourceAction(
        source.id,
        { config: updatedConfig },
        spaceId,
      )
      if (!result.success) {
        toast.error(result.error)
        return
      }
      toast.success('AI configuration updated')
      onOpenChange(false)
      router.refresh()
    } catch (error) {
      console.error('Failed to update AI configuration', error)
      toast.error('Failed to update AI configuration')
    } finally {
      setIsSaving(false)
    }
  }

  const isAiManaged = form.watch('is_ai_managed')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Configure AI agent</DialogTitle>
          <DialogDescription>
            Control how the AI agent builds ingestion queries for this source.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
            <FormField
              control={form.control}
              name="is_ai_managed"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-md border p-3">
                  <div className="space-y-0.5">
                    <FormLabel>AI-managed queries</FormLabel>
                    <FormDescription>
                      Let the agent generate optimized search queries automatically.
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />

            {isAiManaged && (
              <AiManagedConfigFields form={form} />
            )}

            {isPubMedSource && <PubMedConfigFields form={form} />}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 size-4 animate-spin" />}
                Save configuration
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
