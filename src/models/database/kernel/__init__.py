# Kernel Database Models - Metadata-Driven Graph Kernel
#
# NOTE: Workspace scoping is handled by the existing ResearchSpace models
# (``src/models/database/research_space.py``). The kernel itself provides
# dictionary + fact tables (entities/observations/relations/provenance).

from .concepts import (
    ConceptAliasModel,
    ConceptDecisionModel,
    ConceptHarnessResultModel,
    ConceptLinkModel,
    ConceptMemberModel,
    ConceptPolicyModel,
    ConceptSetModel,
)
from .dictionary import (
    DictionaryChangelogModel,
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    DictionarySensitivityLevelModel,
    EntityResolutionPolicyModel,
    RelationConstraintModel,
    TransformRegistryModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from .entities import EntityIdentifierModel, EntityModel
from .observations import ObservationModel
from .provenance import ProvenanceModel
from .relation_claims import RelationClaimModel
from .relations import RelationEvidenceModel, RelationModel

__all__ = [
    # Dictionary (Layer 1)
    "DictionaryChangelogModel",
    "DictionaryDataTypeModel",
    "DictionaryDomainContextModel",
    "DictionaryEntityTypeModel",
    "DictionaryRelationSynonymModel",
    "DictionaryRelationTypeModel",
    "DictionarySensitivityLevelModel",
    "VariableDefinitionModel",
    "VariableSynonymModel",
    "TransformRegistryModel",
    "ValueSetModel",
    "ValueSetItemModel",
    "EntityResolutionPolicyModel",
    "RelationConstraintModel",
    # Concept Manager
    "ConceptAliasModel",
    "ConceptDecisionModel",
    "ConceptHarnessResultModel",
    "ConceptLinkModel",
    "ConceptMemberModel",
    "ConceptPolicyModel",
    "ConceptSetModel",
    # Core Data (Layer 2)
    "EntityModel",
    "EntityIdentifierModel",
    "ObservationModel",
    "RelationEvidenceModel",
    "RelationClaimModel",
    "RelationModel",
    "ProvenanceModel",
]
