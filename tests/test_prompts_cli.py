import pytest

from docintel.cli import main
from docintel.prompts import PROMPTS, get_prompt


def test_prompt_versions_render():
    for version in PROMPTS:
        msgs = get_prompt(version).render("DOC TEXT")
        assert msgs[0]["role"] == "system" and "DOC TEXT" in msgs[1]["content"]


def test_unknown_prompt():
    with pytest.raises(KeyError):
        get_prompt("v99")


def test_cli_generate(tmp_path, capsys):
    assert main(["generate", "--out", str(tmp_path)]) == 0
    assert len(list((tmp_path / "raw").iterdir())) == 24
    assert "wrote 24 documents" in capsys.readouterr().out
