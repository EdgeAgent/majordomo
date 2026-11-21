"""Office document tools: Word, PowerPoint, Excel.

Create and read ``.docx`` / ``.pptx`` / ``.xlsx`` files inside the
workspace. The libraries (python-docx, python-pptx, openpyxl) sit
behind the ``documents`` optional extra — the core install never
requires them, and the imports here are lazy: without the extra, the
tools return a clear install hint instead of crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .filetools import Workspace
from .tools import Tool, ToolRegistry

_INSTALL_HINT = (
    'The documents extra is not installed. Run: pip install "majordomo[documents]" '
    "(or add python-docx, python-pptx, and openpyxl to your environment)."
)


def _require(module: str) -> Any:
    try:
        return __import__(module)
    except ImportError as exc:
        raise RuntimeError(_INSTALL_HINT) from exc


def create_word_doc(workspace: Workspace, filename: str, title: str, paragraphs: list[str]) -> str:
    """Create a .docx with a heading and body paragraphs."""
    docx = _require("docx")
    path = workspace.resolve(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = docx.Document()
    document.add_heading(title, level=0)
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(str(path))
    return f"Created Word document {Path(filename).name} ({len(paragraphs)} paragraphs)."


def create_powerpoint(
    workspace: Workspace, filename: str, title: str, slides: list[dict[str, Any]]
) -> str:
    """Create a .pptx: a title slide plus one slide per entry."""
    pptx = _require("pptx")
    path = workspace.resolve(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    presentation = pptx.Presentation()
    title_slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    title_slide.shapes.title.text = title
    for slide_spec in slides:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = str(slide_spec.get("title", ""))
        body = slide.placeholders[1].text_frame
        bullets = [str(b) for b in slide_spec.get("bullets", [])]
        if bullets:
            body.text = bullets[0]
            for bullet in bullets[1:]:
                body.add_paragraph().text = bullet
    presentation.save(str(path))
    return f"Created PowerPoint {Path(filename).name} ({len(slides) + 1} slides)."


def create_spreadsheet(
    workspace: Workspace, filename: str, sheet_name: str, rows: list[list[Any]]
) -> str:
    """Create an .xlsx with the given rows on one sheet."""
    openpyxl = _require("openpyxl")
    path = workspace.resolve(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name or "Sheet1"
    for row in rows:
        sheet.append(list(row))
    workbook.save(str(path))
    return f"Created spreadsheet {Path(filename).name} ({len(rows)} rows)."


def read_document(workspace: Workspace, filename: str) -> str:
    """Extract the text of a .docx, .pptx, or .xlsx in the workspace."""
    path = workspace.resolve(filename)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        docx = _require("docx")
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs if p.text)
    if suffix == ".pptx":
        pptx = _require("pptx")
        presentation = pptx.Presentation(str(path))
        lines: list[str] = []
        for number, slide in enumerate(presentation.slides, 1):
            lines.append(f"--- Slide {number} ---")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        lines.append(text)
        return "\n".join(lines)
    if suffix == ".xlsx":
        openpyxl = _require("openpyxl")
        workbook = openpyxl.load_workbook(str(path), read_only=True)
        lines = []
        for sheet in workbook.worksheets:
            lines.append(f"--- Sheet: {sheet.title} ---")
            for row in sheet.iter_rows(values_only=True):
                lines.append(" | ".join("" if c is None else str(c) for c in row))
        return "\n".join(lines)
    raise ValueError(f"Cannot read {suffix or 'extensionless'} files; use .docx, .pptx, or .xlsx.")


def register_document_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    """Add create_word_doc / create_powerpoint / create_spreadsheet / read_document."""

    def word(filename: str, title: str, paragraphs: list[str]) -> str:
        return create_word_doc(workspace, filename, title, paragraphs)

    def deck(filename: str, title: str, slides: list[dict[str, Any]]) -> str:
        return create_powerpoint(workspace, filename, title, slides)

    def sheet(filename: str, sheet_name: str, rows: list[list[Any]]) -> str:
        return create_spreadsheet(workspace, filename, sheet_name, rows)

    def read(filename: str) -> str:
        return read_document(workspace, filename)

    registry.register(
        Tool(
            name="create_word_doc",
            description="Create a Word (.docx) document in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "title": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["filename", "title", "paragraphs"],
            },
            handler=word,
        )
    )
    registry.register(
        Tool(
            name="create_powerpoint",
            description="Create a PowerPoint (.pptx) deck in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "title": {"type": "string"},
                    "slides": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["filename", "title", "slides"],
            },
            handler=deck,
        )
    )
    registry.register(
        Tool(
            name="create_spreadsheet",
            description="Create an Excel (.xlsx) spreadsheet in the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "sheet_name": {"type": "string"},
                    "rows": {"type": "array", "items": {"type": "array"}},
                },
                "required": ["filename", "sheet_name", "rows"],
            },
            handler=sheet,
        )
    )
    registry.register(
        Tool(
            name="read_document",
            description="Read the text of a .docx, .pptx, or .xlsx in the workspace.",
            parameters={
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
            handler=read,
            read_only=True,
        )
    )
