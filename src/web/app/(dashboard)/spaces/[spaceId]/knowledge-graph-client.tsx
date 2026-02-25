'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'

import { DashboardSection } from '@/components/ui/composition-patterns'
import { Button } from '@/components/ui/button'

import { KnowledgeGraphFeedbackCards } from './knowledge-graph-feedback-cards'
import { KnowledgeGraphFiltersCard } from './knowledge-graph-filters-card'
import { KnowledgeGraphLegacyTables } from './knowledge-graph-legacy-tables'
import { KnowledgeGraphQueryCard } from './knowledge-graph-query-card'
import { KnowledgeGraphSearchResultsCard } from './knowledge-graph-search-results-card'
import { KnowledgeGraphVisualization } from './knowledge-graph-visualization'
import { useKnowledgeGraphController } from './use-knowledge-graph-controller'

interface KnowledgeGraphClientProps {
  spaceId: string
  initialQuestion?: string
  initialTopK?: number
  initialMaxDepth?: number
  initialForceAgent?: boolean
}

export default function KnowledgeGraphClient({
  spaceId,
  initialQuestion = '',
  initialTopK = 25,
  initialMaxDepth = 2,
  initialForceAgent = false,
}: KnowledgeGraphClientProps) {
  const router = useRouter()
  const { data: session } = useSession()
  const token = session?.user?.access_token
  const controller = useKnowledgeGraphController({
    spaceId,
    token,
    router,
    initialQuestion,
    initialTopK,
    initialMaxDepth,
    initialForceAgent,
  })

  return (
    <div className="space-y-6">
      <DashboardSection
        title="Knowledge Graph"
        description="Explore the kernel graph (entities + relations) for this research space."
        actions={
          <Button asChild variant="outline">
            <Link href={`/spaces/${spaceId}/curation`}>Curation</Link>
          </Button>
        }
      >
        <div className="space-y-6">
          <KnowledgeGraphQueryCard
            questionInput={controller.questionInput}
            topKInput={controller.topKInput}
            maxDepthInput={controller.maxDepthInput}
            forceAgent={controller.forceAgent}
            minDepth={controller.minDepth}
            maxDepth={controller.maxDepthLimit}
            minTopK={controller.minTopK}
            maxTopK={controller.maxTopKLimit}
            isLoading={controller.isLoading}
            onQuestionInputChange={controller.setQuestionInput}
            onTopKInputChange={controller.setTopKInput}
            onMaxDepthInputChange={controller.setMaxDepthInput}
            onForceAgentChange={controller.setForceAgent}
            onSearch={controller.runSearch}
            onLoadStarter={controller.resetToStarter}
            onResetFilters={controller.resetFilters}
          />

          <KnowledgeGraphFeedbackCards
            graphSearchError={controller.graphSearchError}
            graphError={controller.graphError}
            graphNotice={controller.graphNotice}
          />

          <KnowledgeGraphVisualization
            filteredGraph={controller.filteredGraph}
            renderGraph={controller.renderGraph}
            subgraphMeta={controller.subgraphMeta}
            truncationNotice={controller.truncationNotice}
            preCapNodeCount={controller.preCapNodeCount}
            preCapEdgeCount={controller.preCapEdgeCount}
            isExpandingNodeId={controller.isExpandingNodeId}
            neighborhood={controller.neighborhood}
            selectedNodeId={controller.selectedNodeId}
            onNodeClick={controller.onNodeClick}
            onHoverNodeChange={controller.onHoverNodeChange}
            onClearSelection={controller.clearSelection}
          />

          <KnowledgeGraphFiltersCard
            availableRelationTypes={controller.availableRelationTypes}
            availableCurationStatuses={controller.availableCurationStatuses}
            relationTypeFilter={controller.relationTypeFilter}
            curationStatusFilter={controller.curationStatusFilter}
            onRelationTypeToggle={controller.toggleRelationType}
            onCurationStatusToggle={controller.toggleCurationStatus}
          />

          <KnowledgeGraphSearchResultsCard graphSearch={controller.graphSearch} />

          <KnowledgeGraphLegacyTables
            renderGraph={controller.renderGraph}
            showRelationTable={controller.showRelationTable}
            showEntityTable={controller.showEntityTable}
            onShowRelationTableChange={controller.setShowRelationTable}
            onShowEntityTableChange={controller.setShowEntityTable}
          />
        </div>
      </DashboardSection>
    </div>
  )
}
