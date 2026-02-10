# Kernel Database Models - Universal Study Graph Platform
# These models implement the metadata-driven kernel schema
# that replaces the old domain-specific entity tables.

from .dictionary import (
    EntityResolutionPolicyModel,
    RelationConstraintModel,
    TransformRegistryModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from .entities import EntityIdentifierModel, EntityModel
from .observations import ObservationModel
from .provenance import ProvenanceModel
from .relations import RelationModel
from .study import StudyMembershipModel, StudyModel

__all__ = [
    # Dictionary (Layer 1)
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Core Data (Layer 2)
    "StudyModel",
    "StudyMembershipModel",
    "EntityModel",
    "EntityIdentifierModel",
    "ObservationModel",
    "RelationModel",
    "ProvenanceModel",
]
