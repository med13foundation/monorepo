// Research Spaces types for the Next.js frontend

export enum SpaceStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ARCHIVED = 'archived',
  SUSPENDED = 'suspended',
}

export enum MembershipRole {
  OWNER = 'owner',
  ADMIN = 'admin',
  CURATOR = 'curator',
  RESEARCHER = 'researcher',
  VIEWER = 'viewer',
}

export interface ResearchSpaceSettings {
  auto_approve?: boolean
  require_review?: boolean
  review_threshold?: number
  relation_governance_mode?: 'FULL_AUTO' | 'HUMAN_IN_LOOP'
  relation_default_review_threshold?: number
  relation_review_thresholds?: Record<string, number>
  dictionary_agent_creation_policy?: 'ACTIVE' | 'PENDING_REVIEW'
  max_data_sources?: number
  allowed_source_types?: string[]
  public_read?: boolean
  allow_invites?: boolean
  email_notifications?: boolean
  notification_frequency?: string
  custom?: Record<string, string | number | boolean | null>
}

export interface ResearchSpace {
  id: string
  slug: string
  name: string
  description: string
  owner_id: string
  status: SpaceStatus
  settings: ResearchSpaceSettings
  tags: string[]
  created_at: string
  updated_at: string
}

export interface ResearchSpaceMembership {
  id: string
  space_id: string
  user_id: string
  role: MembershipRole
  invited_by: string | null
  invited_at: string | null
  joined_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

// Request types
export interface CreateSpaceRequest {
  name: string
  slug: string
  description?: string
  settings?: ResearchSpaceSettings
  tags?: string[]
}

export interface UpdateSpaceRequest {
  slug?: string
  name?: string
  description?: string
  settings?: ResearchSpaceSettings
  tags?: string[]
  status?: SpaceStatus
}

export interface InviteMemberRequest {
  user_id: string
  role: MembershipRole
}

export interface UpdateMemberRoleRequest {
  role: MembershipRole
}

// Response types
export interface ResearchSpaceListResponse {
  spaces: ResearchSpace[]
  total: number
  skip: number
  limit: number
}

export interface MembershipListResponse {
  memberships: ResearchSpaceMembership[]
  total: number
  skip: number
  limit: number
}

// Extended types with user info (for member lists)
export interface MembershipWithUser extends ResearchSpaceMembership {
  user?: {
    id: string
    email: string
    username: string
    full_name: string
  }
}
