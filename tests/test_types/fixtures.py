"""
Typed test fixtures for MED13 Resource Library.

Provides type-safe test data using NamedTuple and TypedDict structures
for reliable, self-documenting test data.
"""

from datetime import UTC, datetime
from typing import NamedTuple
from uuid import UUID, uuid4

from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters
from src.domain.entities.data_discovery_session import DataDiscoverySession

# Test data types using NamedTuple for immutable, typed test data


class TestPublication(NamedTuple):
    """Typed test publication data."""

    title: str
    authors: list[str]
    journal: str | None
    publication_year: int
    doi: str | None
    pmid: str | None
    abstract: str | None
    created_at: datetime
    updated_at: datetime


class TestResearchSpace(NamedTuple):
    """Typed test research space data."""

    id: UUID
    slug: str
    name: str
    description: str
    owner_id: UUID
    status: str
    settings: dict[str, object]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class TestResearchSpaceMembership(NamedTuple):
    """Typed test research space membership data."""

    id: UUID
    space_id: UUID
    user_id: UUID
    role: str
    invited_by: UUID | None
    invited_at: datetime | None
    joined_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TestSpaceSourcePermission(NamedTuple):
    """Typed test data for space-source permission relationships."""

    space_id: UUID
    source_id: str
    permission_level: str


# Factory functions for creating test data with defaults


def create_test_publication(
    title: str = "Novel MED13 pathogenic variant causes intellectual disability",
    authors: list[str] | None = None,
    journal: str | None = "American Journal of Human Genetics",
    publication_year: int = 2023,
    doi: str | None = "10.1016/j.ajhg.2023.01.001",
    pmid: str | None = "36736399",
    abstract: str | None = None,
) -> TestPublication:
    """
    Create a typed test publication with sensible defaults.

    Args:
        title: Publication title
        authors: List of authors
        journal: Journal name
        publication_year: Year of publication
        doi: DOI identifier
        pmid: PubMed ID
        abstract: Publication abstract

    Returns:
        Typed test publication data
    """
    if authors is None:
        authors = ["Smith J", "Johnson A", "Williams B"]

    if abstract is None:
        abstract = "We report a novel pathogenic variant in MED13 associated with intellectual disability..."

    now = datetime.now(UTC)
    return TestPublication(
        title=title,
        authors=authors,
        journal=journal,
        publication_year=publication_year,
        doi=doi,
        pmid=pmid,
        abstract=abstract,
        created_at=now,
        updated_at=now,
    )


# Pre-defined test data instances


TEST_PUBLICATION_MED13 = create_test_publication()
TEST_PUBLICATION_REVIEW = create_test_publication(
    title="MED13 and intellectual disability: a comprehensive review",
    authors=["Brown C", "Davis M", "Garcia R", "Miller T"],
    journal="Human Molecular Genetics",
    publication_year=2022,
    doi="10.1093/hmg/ddac123",
    pmid="35640231",
)


def create_test_research_space(
    space_id: UUID | None = None,
    slug: str = "med13-research",
    name: str = "MED13 Research Space",
    description: str = "Research space for MED13 syndrome studies",
    owner_id: UUID | None = None,
    status: str = "active",
    settings: dict[str, object] | None = None,
    tags: list[str] | None = None,
) -> TestResearchSpace:
    """
    Create a typed test research space with sensible defaults.

    Args:
        space_id: Research space identifier (generated if not provided)
        slug: URL-safe unique identifier
        name: Display name
        description: Space description
        owner_id: User ID of the space owner (generated if not provided)
        status: Space status (active, inactive, archived, suspended)
        settings: Space-specific settings
        tags: Searchable tags

    Returns:
        Typed test research space data
    """
    if space_id is None:
        space_id = uuid4()
    if owner_id is None:
        owner_id = uuid4()
    if settings is None:
        settings = {}
    if tags is None:
        tags = ["med13", "research", "syndrome"]

    now = datetime.now(UTC)
    return TestResearchSpace(
        id=space_id,
        slug=slug,
        name=name,
        description=description,
        owner_id=owner_id,
        status=status,
        settings=settings,
        tags=tags,
        created_at=now,
        updated_at=now,
    )


def create_test_research_space_membership(
    membership_id: UUID | None = None,
    space_id: UUID | None = None,
    user_id: UUID | None = None,
    role: str = "viewer",
    invited_by: UUID | None = None,
    invited_at: datetime | None = None,
    joined_at: datetime | None = None,
    *,
    is_active: bool = True,
) -> TestResearchSpaceMembership:
    """
    Create a typed test research space membership with sensible defaults.

    Args:
        membership_id: Membership identifier (generated if not provided)
        space_id: Research space ID (generated if not provided)
        user_id: User ID (generated if not provided)
        role: User's role (owner, admin, curator, researcher, viewer)
        invited_by: User ID who sent the invitation
        invited_at: When the invitation was sent
        joined_at: When the user joined
        is_active: Whether the membership is active

    Returns:
        Typed test research space membership data
    """
    if membership_id is None:
        membership_id = uuid4()
    if space_id is None:
        space_id = uuid4()
    if user_id is None:
        user_id = uuid4()

    now = datetime.now(UTC)
    return TestResearchSpaceMembership(
        id=membership_id,
        space_id=space_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by,
        invited_at=invited_at,
        joined_at=joined_at,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


# Space-scoped permission fixtures
def create_test_space_source_permissions(
    *,
    space_id: UUID | None = None,
    second_space_id: UUID | None = None,
) -> list[TestSpaceSourcePermission]:
    """
    Create a pair of test permissions demonstrating allowed vs blocked sources.

    Args:
        space_id: Primary research space identifier
        second_space_id: Secondary space identifier

    Returns:
        List of permission fixtures covering available/blocked cases
    """
    primary_space = space_id or uuid4()
    secondary_space = second_space_id or uuid4()
    return [
        TestSpaceSourcePermission(
            space_id=primary_space,
            source_id="clinvar",
            permission_level="available",
        ),
        TestSpaceSourcePermission(
            space_id=secondary_space,
            source_id="clinvar",
            permission_level="blocked",
        ),
    ]


def create_test_space_discovery_session(
    space_id: UUID,
    *,
    owner_id: UUID | None = None,
    name: str = "Space Discovery Session",
    current_parameters: AdvancedQueryParameters | None = None,
    selected_sources: list[str] | None = None,
    tested_sources: list[str] | None = None,
) -> DataDiscoverySession:
    """
    Create a discovery session fixture bound to a specific research space.
    """
    now = datetime.now(UTC)
    return DataDiscoverySession(
        id=uuid4(),
        owner_id=owner_id or uuid4(),
        research_space_id=space_id,
        name=name,
        current_parameters=current_parameters
        or AdvancedQueryParameters(
            gene_symbol="MED13L",
            search_term="atrial defect",
        ),
        selected_sources=selected_sources or [],
        tested_sources=tested_sources or [],
        total_tests_run=len(tested_sources or []),
        successful_tests=len(tested_sources or []),
        is_active=True,
        created_at=now,
        updated_at=now,
        last_activity_at=now,
    )


# Pre-defined research space test instances
TEST_RESEARCH_SPACE_MED13 = create_test_research_space(
    slug="med13-research",
    name="MED13 Research Space",
    description="Primary research space for MED13 syndrome",
    tags=["med13", "syndrome", "research"],
)

TEST_RESEARCH_SPACE_MED12 = create_test_research_space(
    slug="med12-research",
    name="MED12 Research Space",
    description="Research space for MED12 syndrome",
    tags=["med12", "syndrome", "research"],
)

TEST_MEMBERSHIP_OWNER = create_test_research_space_membership(
    role="owner",
    is_active=True,
)

TEST_MEMBERSHIP_ADMIN = create_test_research_space_membership(
    role="admin",
    is_active=True,
)

TEST_MEMBERSHIP_PENDING = create_test_research_space_membership(
    role="viewer",
    invited_at=datetime.now(UTC),
    joined_at=None,
    is_active=True,
)
