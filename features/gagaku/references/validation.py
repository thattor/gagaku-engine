"""Read-only validation of the gagaku reference corpus metadata contract."""

from pathlib import Path
import re

from app.json_documents import DocumentError, load_json_document, validate_document


HERE = Path(__file__).resolve().parent
DEFAULT_CORPUS = HERE / "data/reference-corpus.v0.1.json"
SCHEMA_PATH = HERE / "corpus.schema.json"
_SCHEMA = load_json_document(SCHEMA_PATH)
_ID = re.compile(_SCHEMA["$defs"]["entry"]["properties"]["entry_id"]["pattern"])


def _validate_id(value: str) -> None:
    # JSON Schema's `$` can match before a final newline; IDs must match in full.
    if _ID.fullmatch(value) is None:
        raise DocumentError("corpus_invalid_id")


def validate_corpus(data: dict) -> None:
    """Check structure and references without judging rights authenticity.

    Record counts are unrestricted. Whether a listed DOI is genuine, whether
    a rights category matches reality, and whether any permission was truly
    obtained are outside this static data check.
    """
    validate_document(data, _SCHEMA)
    sources = data["sources"]
    for source_id in sources:
        _validate_id(source_id)

    entry_ids: set[str] = set()
    for entry in data["entries"]:
        identifier = entry["entry_id"]
        _validate_id(identifier)
        if identifier in entry_ids:
            raise DocumentError("corpus_duplicate_entry_id")
        entry_ids.add(identifier)

        source_ref = entry["source_ref"]
        _validate_id(source_ref)
        if source_ref not in sources:
            raise DocumentError("corpus_unknown_source")

        evidence = entry["evidence"]
        evidence_source_ref = evidence["source_ref"]
        if evidence_source_ref is not None:
            _validate_id(evidence_source_ref)
            if evidence_source_ref not in sources:
                raise DocumentError("corpus_unknown_source")


def load_corpus(path: Path = DEFAULT_CORPUS) -> dict:
    """Decode and validate a JSON file, rejecting duplicate keys at any depth."""
    data = load_json_document(path)
    validate_corpus(data)
    return data
