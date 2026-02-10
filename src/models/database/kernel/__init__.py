# Kernel Database Models - Metadata-Driven Graph Kernel
#
# NOTE: Workspace scoping is handled by the existing ResearchSpace models
# (``src/models/database/research_space.py``). The kernel itself provides
# dictionary + fact tables (entities/observations/relations/provenance).

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

__all__ = [
    # Dictionary (Layer 1)
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Core Data (Layer 2)
    "EntityModel",
    "EntityIdentifierModel",
    "ObservationModel",
    "RelationModel",
    "ProvenanceModel",
]
