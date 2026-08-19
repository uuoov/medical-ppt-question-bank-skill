#!/usr/bin/env python3
"""Extract slide text, notes, and visual-risk flags from a PPTX as NDJSON."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_items(root: ET.Element) -> list[str]:
    items: list[str] = []
    for node in root.iter(f"{{{A_NS}}}t"):
        value = clean_text(node.text)
        if value:
            items.append(value)
    return items


def notes_items(root: ET.Element) -> list[str]:
    items: list[str] = []
    for shape in root.iter(f"{{{P_NS}}}sp"):
        placeholder = shape.find(f".//{{{P_NS}}}ph")
        placeholder_type = placeholder.get("type") if placeholder is not None else None
        if placeholder_type in {"dt", "ftr", "hdr", "sldNum"}:
            continue
        for node in shape.iter(f"{{{A_NS}}}t"):
            value = clean_text(node.text)
            if value:
                items.append(value)
    return items


def related_notes_path(archive: zipfile.ZipFile, slide_path: str) -> str | None:
    rels_path = posixpath.join(
        posixpath.dirname(slide_path),
        "_rels",
        posixpath.basename(slide_path) + ".rels",
    )
    try:
        root = ET.fromstring(archive.read(rels_path))
    except KeyError:
        return None
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        if (rel.get("Type") or "").endswith("/notesSlide"):
            target = rel.get("Target")
            if target:
                return posixpath.normpath(posixpath.join(posixpath.dirname(slide_path), target))
    return None


def count_related_charts(archive: zipfile.ZipFile, slide_path: str) -> int:
    rels_path = posixpath.join(
        posixpath.dirname(slide_path),
        "_rels",
        posixpath.basename(slide_path) + ".rels",
    )
    try:
        root = ET.fromstring(archive.read(rels_path))
    except KeyError:
        return 0
    return sum(
        1
        for rel in root.findall(f"{{{REL_NS}}}Relationship")
        if (rel.get("Type") or "").endswith("/chart")
    )


def slide_number(path: str) -> int:
    match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", path)
    if not match:
        raise ValueError(f"Unexpected slide path: {path}")
    return int(match.group(1))


def extract(source: Path) -> list[dict[str, object]]:
    if source.suffix.lower() != ".pptx":
        raise ValueError("Input must be a .pptx file")
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(source) as archive:
        slide_paths = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=slide_number,
        )
        if not slide_paths:
            raise ValueError("No slides found in PPTX")
        archive_names = set(archive.namelist())
        for slide_path in slide_paths:
            root = ET.fromstring(archive.read(slide_path))
            slide_text = text_items(root)
            note_path = related_notes_path(archive, slide_path)
            note_text: list[str] = []
            if note_path and note_path in archive_names:
                note_text = notes_items(ET.fromstring(archive.read(note_path)))
            image_count = sum(1 for _ in root.iter(f"{{{A_NS}}}blip"))
            table_count = sum(1 for _ in root.iter(f"{{{A_NS}}}tbl"))
            chart_count = count_related_charts(archive, slide_path)
            records.append(
                {
                    "slide": slide_number(slide_path),
                    "slide_path": slide_path,
                    "text": "\n".join(slide_text),
                    "text_items": slide_text,
                    "notes": "\n".join(note_text),
                    "notes_items": note_text,
                    "image_count": image_count,
                    "table_count": table_count,
                    "chart_count": chart_count,
                    "needs_visual_review": bool(image_count or table_count or chart_count),
                }
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Input .pptx path")
    parser.add_argument("--output", type=Path, required=True, help="Output .ndjson path")
    args = parser.parse_args()
    if not args.source.is_file():
        parser.error(f"Input file does not exist: {args.source}")
    records = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = {
        "ok": True,
        "slides": len(records),
        "slides_needing_visual_review": sum(bool(r["needs_visual_review"]) for r in records),
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
