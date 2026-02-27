"""
Typed test fixtures and mocks for MED13 Resource Library.

Provides type-safe test data and factory functions for comprehensive testing.
"""

from .fixtures import (
    TEST_MEMBERSHIP_ADMIN,
    TEST_MEMBERSHIP_OWNER,
    TEST_MEMBERSHIP_PENDING,
    TEST_RESEARCH_SPACE_MED12,
    TEST_RESEARCH_SPACE_MED13,
    TestPublication,
    TestResearchSpace,
    TestResearchSpaceMembership,
    create_test_publication,
    create_test_research_space,
    create_test_research_space_membership,
)
from .mocks import (
    MockPublicationRepository,
)

__all__ = [
    "MockPublicationRepository",
    "TEST_MEMBERSHIP_ADMIN",
    "TEST_MEMBERSHIP_OWNER",
    "TEST_MEMBERSHIP_PENDING",
    "TEST_RESEARCH_SPACE_MED12",
    "TEST_RESEARCH_SPACE_MED13",
    "TestPublication",
    "TestResearchSpace",
    "TestResearchSpaceMembership",
    "create_test_publication",
    "create_test_research_space",
    "create_test_research_space_membership",
]
