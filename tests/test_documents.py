"""Document tools: real files, created and reopened."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("docx")
pytest.importorskip("pptx")
pytest.importorskip("openpyxl")

from majordomo.doctoolkit import (
    create_powerpoint,
    create_spreadsheet,
    create_word_doc,
    read_document,
)
from majordomo.filetools import Workspace


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace")


def test_word_doc_roundtrip(workspace: Workspace) -> None:
    result = create_word_doc(
        workspace, "brief.docx", "Pilot Brief", ["First body paragraph.", "Second body paragraph."]
    )
    assert "brief.docx" in result
    path = workspace.root / "brief.docx"
    assert path.exists() and path.stat().st_size > 0
    text = read_document(workspace, "brief.docx")
    assert "Pilot Brief" in text
    assert "First body paragraph." in text


def test_word_doc_reopens_with_python_docx(workspace: Workspace) -> None:
    import docx

    create_word_doc(workspace, "check.docx", "Title Here", ["Body text"])
    document = docx.Document(str(workspace.root / "check.docx"))
    texts = [p.text for p in document.paragraphs]
    assert "Title Here" in texts
    assert "Body text" in texts


def test_powerpoint_roundtrip(workspace: Workspace) -> None:
    result = create_powerpoint(
        workspace,
        "deck.pptx",
        "Quarterly",
        [
            {"title": "Wins", "bullets": ["Shipped the thing", "No fires"]},
            {"title": "Next", "bullets": ["Keep going"]},
        ],
    )
    assert "3 slides" in result
    text = read_document(workspace, "deck.pptx")
    assert "Quarterly" in text
    assert "Shipped the thing" in text
    assert "Slide 3" in text


def test_spreadsheet_roundtrip(workspace: Workspace) -> None:
    result = create_spreadsheet(
        workspace, "data.xlsx", "Numbers", [["Item", "Qty"], ["Bolts", 40], ["Beams", 6]]
    )
    assert "3 rows" in result
    text = read_document(workspace, "data.xlsx")
    assert "Bolts | 40" in text
    assert "Sheet: Numbers" in text


def test_read_unsupported_suffix_errors(workspace: Workspace) -> None:
    workspace.write("notes.txt", "plain")
    with pytest.raises(ValueError, match="Cannot read"):
        read_document(workspace, "notes.txt")


def test_document_tools_cannot_escape_workspace(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="escapes the workspace"):
        create_word_doc(workspace, "../evil.docx", "Nope", ["x"])
