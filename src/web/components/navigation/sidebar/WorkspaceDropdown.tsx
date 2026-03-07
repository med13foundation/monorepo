"use client"

import * as React from "react"
import { ChevronsUpDown } from "lucide-react"

import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { BrandLogo } from "@/components/branding/BrandLogo"
import { SpaceSelectorModal } from "@/components/research-spaces/SpaceSelectorModal"
import { DASHBOARD_LABEL } from "@/lib/branding"
import type { ResearchSpace } from "@/types/research-space"

interface WorkspaceDropdownProps {
  /** Currently selected space (null if on dashboard) */
  currentSpace: ResearchSpace | null
  /** List of available spaces */
  spaces: ResearchSpace[]
  /** Logo configuration */
  logo: {
    src: string
    alt: string
    width: number
    height: number
  }
}

export function WorkspaceDropdown({
  currentSpace,
  spaces,
  logo,
}: WorkspaceDropdownProps) {
  const [modalOpen, setModalOpen] = React.useState(false)

  // Display label based on context
  const displayLabel = currentSpace?.name || DASHBOARD_LABEL
  const displaySlug = currentSpace?.slug || "All Spaces"

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            onClick={() => setModalOpen(true)}
            aria-label={displayLabel}
            className="gap-3 rounded-2xl bg-brand-primary/5 px-3 py-2.5 text-foreground transition-colors hover:bg-brand-primary/10 data-[state=open]:bg-brand-primary/15 data-[state=open]:text-foreground group-data-[collapsible=icon]:!justify-center group-data-[collapsible=icon]:!gap-0"
          >
            <div className="flex aspect-square size-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white/90 dark:bg-[#0F1C22]">
              <BrandLogo
                alt={logo.alt}
                width={logo.width}
                height={logo.height}
                className="size-8"
              />
            </div>
            <div className="grid min-w-0 flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
              <span className="truncate font-semibold tracking-[-0.01em] text-foreground">{displayLabel}</span>
              <span className="truncate pt-0.5 text-[11px] text-muted-foreground">
                {displaySlug}
              </span>
            </div>
            <ChevronsUpDown className="ml-1 size-4 shrink-0 text-muted-foreground group-data-[collapsible=icon]:hidden" />
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>

      <SpaceSelectorModal
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </>
  )
}
