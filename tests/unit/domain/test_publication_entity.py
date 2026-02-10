from src.domain.entities.publication import Publication, PublicationType
from src.domain.value_objects.identifiers import PublicationIdentifier


def build_publication() -> Publication:
    identifier = PublicationIdentifier(pubmed_id="12345678")
    return Publication(
        identifier=identifier,
        title="Insights into MED13",
        authors=("Smith A", "Doe B"),
        journal="Genetics Journal",
        publication_year=2023,
        publication_type=PublicationType.JOURNAL_ARTICLE,
        keywords=("med13", "genetics"),
    )


def test_publication_relevance_validation() -> None:
    publication = build_publication()
    publication.update_relevance(5)
    assert publication.relevance_score == 5
