import json

from docintel.data_gen import generate, write_sample
from docintel.schemas import consistency_issues, validate_payload


def test_generation_is_deterministic():
    a, b = generate(seed=7), generate(seed=7)
    assert [d.content for d in a] == [d.content for d in b]
    assert [d.content for d in generate(seed=8)] != [d.content for d in a]


def test_labels_are_valid_and_consistent():
    for d in generate():
        model, errors = validate_payload(d.label)
        assert errors == [], (d.doc_id, errors)
        assert consistency_issues(model) == [], d.doc_id


def test_committed_sample_matches_generator(tmp_path, sample_dir):
    write_sample(tmp_path)
    for p in (tmp_path / "labels").glob("*.json"):
        assert json.loads(p.read_text()) == json.loads((sample_dir / "labels" / p.name).read_text())
    for p in (tmp_path / "raw").iterdir():
        assert p.read_text() == (sample_dir / "raw" / p.name).read_text()


def test_mix_of_document_types():
    types = {d.label["doc_type"] for d in generate()}
    assert types == {"invoice", "purchase_order", "contract"}
