"""Pydantic schemas for research space routes."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from src.domain.entities.research_space import ResearchSpace
from src.domain.entities.research_space_membership import ResearchSpaceMembership
from src.domain.entities.user import User
from src.domain.entities.user_data_source import SourceConfiguration, UserDataSource
from src.type_definitions.common import JSONObject


class ResearchSpaceResponse(BaseModel):
    """Response model for research space."""

    id: UUID
    slug: str
    name: str
    description: str
    owner_id: UUID
    status: str
    settings: JSONObject
    tags: list[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, space: ResearchSpace) -> ResearchSpaceResponse:
        """Create response from domain entity."""
        return cls(
            id=space.id,
            slug=space.slug,
            name=space.name,
            description=space.description,
            owner_id=space.owner_id,
            status=space.status.value,
            settings=dict(space.settings),
            tags=space.tags,
            created_at=space.created_at.isoformat(),
            updated_at=space.updated_at.isoformat(),
        )


class ResearchSpaceListResponse(BaseModel):
    """Response model for list of research spaces."""

    spaces: list[ResearchSpaceResponse]
    total: int
    skip: int
    limit: int


class MembershipUserResponse(BaseModel):
    """Compact user profile included with membership responses."""

    id: UUID
    email: str
    username: str
    full_name: str

    @classmethod
    def from_user(cls, user: User) -> MembershipUserResponse:
        """Create a compact membership user payload from a user entity."""
        return cls(
            id=user.id,
            email=str(user.email),
            username=user.username,
            full_name=user.full_name,
        )


class MembershipResponse(BaseModel):
    """Response model for research space membership."""

    id: UUID
    space_id: UUID
    user_id: UUID
    role: str
    invited_by: UUID | None
    invited_at: str | None
    joined_at: str | None
    is_active: bool
    created_at: str
    updated_at: str
    user: MembershipUserResponse | None = None

    @classmethod
    def from_entity(
        cls,
        membership: ResearchSpaceMembership,
        *,
        user: MembershipUserResponse | None = None,
    ) -> MembershipResponse:
        """Create response from domain entity."""
        return cls(
            id=membership.id,
            space_id=membership.space_id,
            user_id=membership.user_id,
            role=membership.role.value,
            invited_by=membership.invited_by,
            invited_at=(
                membership.invited_at.isoformat() if membership.invited_at else None
            ),
            joined_at=(
                membership.joined_at.isoformat() if membership.joined_at else None
            ),
            is_active=membership.is_active,
            created_at=membership.created_at.isoformat(),
            updated_at=membership.updated_at.isoformat(),
            user=user,
        )


class MembershipListResponse(BaseModel):
    """Response model for list of memberships."""

    memberships: list[MembershipResponse]
    total: int
    skip: int
    limit: int


class InvitableUserSearchResponse(BaseModel):
    """Response model for active-user autocomplete in invite flows."""

    query: str
    users: list[MembershipUserResponse]
    total: int
    limit: int


class CreateSpaceRequestModel(BaseModel):
    """Request model for creating a research space."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=3, max_length=50)
    description: str = Field(default="", max_length=500)
    settings: JSONObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class UpdateSpaceRequestModel(BaseModel):
    """Request model for updating a research space."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    settings: JSONObject | None = None
    tags: list[str] | None = None
    status: str | None = None


class InviteMemberRequestModel(BaseModel):
    """Request model for inviting a member."""

    user_id: UUID
    role: str = Field(..., description="Membership role")


class UpdateMemberRoleRequestModel(BaseModel):
    """Request model for updating member role."""

    role: str = Field(..., description="New membership role")


class DataSourceResponse(BaseModel):
    """Response model for data source."""

    id: UUID
    owner_id: UUID
    research_space_id: UUID | None
    name: str
    description: str
    source_type: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, source: UserDataSource) -> DataSourceResponse:
        """Create response from domain entity."""

        return cls(
            id=source.id,
            owner_id=source.owner_id,
            research_space_id=source.research_space_id,
            name=source.name,
            description=source.description,
            source_type=source.source_type.value,
            status=source.status.value,
            created_at=source.created_at.isoformat(),
            updated_at=source.updated_at.isoformat(),
        )


class DataSourceListResponse(BaseModel):
    """Response model for list of data sources."""

    data_sources: list[DataSourceResponse]
    total: int
    skip: int
    limit: int


class CreateDataSourceRequest(BaseModel):
    """Request model for creating a data source in a space."""

    name: str
    description: str = ""
    source_type: str
    config: SourceConfiguration = Field(
        default_factory=lambda: SourceConfiguration.model_validate({}),
    )
    tags: list[str] = Field(default_factory=list)


class CurationStatsResponse(BaseModel):
    """Response model for curation statistics."""

    total: int
    pending: int
    approved: int
    rejected: int


class CurationQueueItemResponse(BaseModel):
    """Response model for curation queue item."""

    id: int
    entity_type: str
    entity_id: str
    status: str
    priority: str
    quality_score: float | None
    issues: int
    last_updated: str | None


class CurationQueueResponse(BaseModel):
    """Response model for curation queue."""

    items: list[CurationQueueItemResponse]
    total: int
    skip: int
    limit: int


class SpaceOverviewDataSourcesResponse(BaseModel):
    """Paginated data source preview for the space overview endpoint."""

    items: list[DataSourceResponse]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool


class SpaceOverviewAccessResponse(BaseModel):
    """Access and role flags used by the space overview UI."""

    has_space_access: bool
    can_manage_members: bool
    can_edit_space: bool
    is_owner: bool
    show_membership_notice: bool
    effective_role: str


class SpaceOverviewCountsResponse(BaseModel):
    """Lightweight counts for common space overview widgets."""

    member_count: int
    data_source_count: int


class SpaceOverviewResponse(BaseModel):
    """Aggregated payload for space overview rendering."""

    space: ResearchSpaceResponse
    membership: MembershipResponse | None
    access: SpaceOverviewAccessResponse
    counts: SpaceOverviewCountsResponse
    data_sources: SpaceOverviewDataSourcesResponse
    curation_stats: CurationStatsResponse
    curation_queue: CurationQueueResponse
