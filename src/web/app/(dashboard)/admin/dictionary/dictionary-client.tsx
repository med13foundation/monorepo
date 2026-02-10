"use client"

import { useRouter } from 'next/navigation'
import { RefreshCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  EntityResolutionPolicyListResponse,
  RelationConstraintListResponse,
  TransformRegistryListResponse,
  VariableDefinitionListResponse,
} from '@/types/dictionary'

import { CreateVariableCard } from './variable-create-card'
import { VariablesTableCard } from './variables-table-card'
import { TransformsTableCard } from './transforms-table-card'
import { PoliciesTableCard } from './policies-table-card'
import { ConstraintsTableCard } from './constraints-table-card'

interface DictionaryClientProps {
  variables: VariableDefinitionListResponse | null
  variablesError?: string | null
  transforms: TransformRegistryListResponse | null
  transformsError?: string | null
  policies: EntityResolutionPolicyListResponse | null
  policiesError?: string | null
  constraints: RelationConstraintListResponse | null
  constraintsError?: string | null
}

export default function DictionaryClient({
  variables,
  variablesError,
  transforms,
  transformsError,
  policies,
  policiesError,
  constraints,
  constraintsError,
}: DictionaryClientProps) {
  const router = useRouter()

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold">Dictionary</h1>
          <p className="text-sm text-muted-foreground">
            Manage the kernel dictionary: variables, transforms, resolution policies, and relation constraints.
          </p>
        </div>
        <Button variant="outline" onClick={() => router.refresh()} className="w-full sm:w-auto">
          <RefreshCcw className="mr-2 size-4" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="variables">
        <TabsList>
          <TabsTrigger value="variables">Variables</TabsTrigger>
          <TabsTrigger value="transforms">Transforms</TabsTrigger>
          <TabsTrigger value="policies">Resolution Policies</TabsTrigger>
          <TabsTrigger value="constraints">Relation Constraints</TabsTrigger>
        </TabsList>

        <TabsContent value="variables" className="mt-4 space-y-4">
          <CreateVariableCard />
          <VariablesTableCard variables={variables} error={variablesError} />
        </TabsContent>

        <TabsContent value="transforms" className="mt-4">
          <TransformsTableCard transforms={transforms} error={transformsError} />
        </TabsContent>

        <TabsContent value="policies" className="mt-4">
          <PoliciesTableCard policies={policies} error={policiesError} />
        </TabsContent>

        <TabsContent value="constraints" className="mt-4">
          <ConstraintsTableCard constraints={constraints} error={constraintsError} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
