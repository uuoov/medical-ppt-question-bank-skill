#!/usr/bin/env python3
"""Validate a source-traceable Chinese medical question-bank CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


COLUMNS = ["题号", "题型", "题目", "选项内容", "标准答案", "解析", "PPT页码", "PPT依据"]
QUESTION_TYPES = {"单选题", "多选题", "判断题"}
OPTION_RE = re.compile(r"(?m)^\s*([A-Z])[.、)]\s*\S")
ANSWER_PREFIX_RE = re.compile(r"^\s*([A-Z](?:[\s,，、/]*[A-Z])*)")
SOURCE_HINT_RE = re.compile(r"(?:根据|按照|参照|结合)?\s*(?:PPT|课件|幻灯片|上述材料).{0,12}(?:第\s*\d+\s*页|中|内容|提到)", re.I)


def item(row: int, field: str, message: str) -> dict[str, object]:
    return {"row": row, "field": field, "message": message}


def normalized_stem(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()


def answer_letters(value: str) -> list[str]:
    match = ANSWER_PREFIX_RE.match(value or "")
    return re.findall(r"[A-Z]", match.group(1)) if match else []


def validate(path: Path, expected: dict[str, int | None], expected_total: int | None) -> dict[str, object]:
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if headers != COLUMNS:
            errors.append(item(1, "表头", f"expected {COLUMNS}, got {headers}"))
        rows = list(reader)

    if not rows:
        errors.append(item(0, "行数", "no question rows"))
    if expected_total is not None and len(rows) != expected_total:
        errors.append(item(0, "行数", f"expected total {expected_total}, got {len(rows)}"))

    counts = Counter((row.get("题型") or "").strip() for row in rows)
    for question_type, wanted in expected.items():
        if wanted is not None and counts.get(question_type, 0) != wanted:
            errors.append(item(0, "题型", f"expected {question_type}={wanted}, got {counts.get(question_type, 0)}"))

    seen_numbers: set[str] = set()
    seen_stems: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        for field in COLUMNS:
            if not (row.get(field) or "").strip():
                errors.append(item(row_number, field, "must not be empty"))

        number = (row.get("题号") or "").strip()
        if number in seen_numbers:
            errors.append(item(row_number, "题号", f"duplicate question number: {number}"))
        seen_numbers.add(number)

        question_type = (row.get("题型") or "").strip()
        if question_type not in QUESTION_TYPES:
            errors.append(item(row_number, "题型", f"unsupported type: {question_type}"))

        stem = (row.get("题目") or "").strip()
        stem_key = normalized_stem(stem)
        if stem_key in seen_stems:
            errors.append(item(row_number, "题目", f"duplicate stem; first seen at row {seen_stems[stem_key]}"))
        else:
            seen_stems[stem_key] = row_number
        if SOURCE_HINT_RE.search(stem):
            errors.append(item(row_number, "题目", "contains a PPT/material source hint; move page information to evidence columns"))

        option_letters = OPTION_RE.findall(row.get("选项内容") or "")
        wanted_letters = [chr(ord("A") + i) for i in range(len(option_letters))]
        if len(option_letters) < 2:
            errors.append(item(row_number, "选项内容", "fewer than two labeled options"))
        elif option_letters != wanted_letters:
            errors.append(item(row_number, "选项内容", f"option labels must be consecutive from A, got {option_letters}"))

        answers = answer_letters(row.get("标准答案") or "")
        if not answers:
            errors.append(item(row_number, "标准答案", "answer must start with one or more option letters"))
        missing = sorted(set(answers) - set(option_letters))
        if missing:
            errors.append(item(row_number, "标准答案", f"answer letters absent from options: {missing}"))
        if len(answers) != len(set(answers)):
            errors.append(item(row_number, "标准答案", "answer contains duplicate letters"))

        if question_type == "单选题" and len(answers) != 1:
            errors.append(item(row_number, "标准答案", "single-choice question must have exactly one answer"))
        elif question_type == "多选题" and len(answers) < 2:
            errors.append(item(row_number, "标准答案", "multiple-choice question must have at least two answers"))
        elif question_type == "判断题":
            if option_letters != ["A", "B"]:
                errors.append(item(row_number, "选项内容", "true/false question must use exactly A and B"))
            if len(answers) != 1 or (answers and answers[0] not in {"A", "B"}):
                errors.append(item(row_number, "标准答案", "true/false answer must be A or B"))
            options = row.get("选项内容") or ""
            if "正确" not in options or "错误" not in options:
                warnings.append(item(row_number, "选项内容", "true/false options should contain 正确 and 错误"))

        if option_letters and question_type == "多选题" and set(answers) == set(option_letters):
            warnings.append(item(row_number, "标准答案", "all options are correct; verify question discrimination"))

    return {
        "ok": not errors,
        "rows": len(rows),
        "counts": dict(counts),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--single", type=int, help="Expected number of single-choice questions")
    parser.add_argument("--multiple", type=int, help="Expected number of multiple-choice questions")
    parser.add_argument("--true-false", type=int, dest="true_false", help="Expected number of true/false questions")
    parser.add_argument("--expected-total", type=int)
    args = parser.parse_args()
    if not args.csv_path.is_file():
        parser.error(f"CSV does not exist: {args.csv_path}")
    expected = {"单选题": args.single, "多选题": args.multiple, "判断题": args.true_false}
    result = validate(args.csv_path, expected, args.expected_total)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
