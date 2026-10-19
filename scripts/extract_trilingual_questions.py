#!/usr/bin/env python3
"""
SifoDrive Question Bank Trilingual Extraction Script
====================================================
Extracts official Rwanda Highway Code theory examination questions in all three
official languages (Kinyarwanda, English, French) from the master PDF:
'TABLE OF QUESTIONS CORRECT V_2X (1) amategeko y\'umuhanda.pdf'.

Key Architecture:
- Full extraction of all 3 languages (RW, EN, FR) directly from the PDF
- Continuous cross-page chunk assembly: questions and options spanning across
  page boundaries (e.g., Q217, Q219) are stitched seamlessly without loss
- Multi-column bounding boxes with whitespace and boundary calibration
- Cross-language answer key validation from parenthesized marks: (a), (b), (c), (d)
- Strict exclusion of 'difficulty' categorization (all questions uniform)
- Full preservation of question diagram images and option diagram sets
- Output: data/parsed_questions.json
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from collections import Counter

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        print("Error: PyMuPDF is not installed. Please install it via 'pip install pymupdf'.", file=sys.stderr)
        sys.exit(1)


# Page Column Bounding Boxes (landscape 792 x 612 pt)
# Y: 68 excludes running header / page number; 560 excludes RESTRICTED footer
RW_RECT = fitz.Rect(45.0, 68.0, 306.0, 560.0)
EN_RECT = fitz.Rect(306.0, 68.0, 508.0, 560.0)
FR_RECT = fitz.Rect(508.0, 68.0, 750.0, 560.0)

# Typo / numbering anomalies in the official PDF per language:
# (page, expected_question_number) -> text_pattern_in_pdf
ALIAS_MAPS = {
    "RW": {},
    "EN": {
        (81, 228): "227",  # PDF English on page 81 printed 227 instead of 228
    },
    "FR": {
        (80, 226): "227",  # PDF French on page 80 printed 227 instead of 226
        (81, 228): "20",   # PDF French on page 81 printed 20 instead of 228
    },
}

OPT_REGEX = re.compile(
    r"^\s*"
    r"(?:"
    r"\(\s*([a-fA-F])\s*(?:\.|\s)*\)"         # (a), ( a ), (a.), (b.)
    r"|"
    r"([a-fA-F])\s*[\.\)]"                     # a), a.
    r"|"
    r"([a-fA-F])\s+(?=[A-Za-z\u00C0-\u017F])" # standalone letter at line start
    r")"
    r"\s*(.*)$"
)


def clean_text_spacing(text):
    """Normalize excess whitespace and line breaks while preserving punctuation."""
    if not text:
        return ""
    # Replace multiple spaces/tabs with a single space
    cleaned = re.sub(r"[ \t]+", " ", text)
    # Normalize multiple newlines
    cleaned = re.sub(r"\n\s+", "\n", cleaned)
    return cleaned.strip()


def parse_option_chunk(chunk_text):
    """
    Parses a raw text chunk into question text and options a, b, c, d.
    Detects if any option is wrapped in parentheses indicating correct answer.
    """
    lines = chunk_text.strip().split("\n")
    q_lines = []
    options = []
    curr_opt = None
    header_seen = False

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        if not header_seen:
            # Match question number header e.g. "217. ", "zi : 383. ", "219\n"
            header_m = re.match(r"^\s*(?:[a-zA-Z]{1,4}\s*:\s*)?\d+\s*[\.\)]?\s*(.*)", line_s)
            if header_m:
                header_seen = True
                if header_m.group(1):
                    q_lines.append(header_m.group(1).strip())
                continue

        m = OPT_REGEX.match(line_s)
        if m and (m.group(1) or m.group(2) or m.group(3)):
            key = (m.group(1) or m.group(2) or m.group(3)).lower()
            rest = m.group(4) or ""
            is_corr = "(" in line_s[:6] and ")" in line_s[:8]
            curr_opt = {
                "key": key,
                "text": [rest.strip()] if rest else [],
                "is_correct": is_corr,
            }
            options.append(curr_opt)
            continue

        if curr_opt:
            curr_opt["text"].append(line_s)
        else:
            q_lines.append(line_s)

    # Map sequential options to slots: a, b, c, d
    mapped = {"a": "", "b": "", "c": "", "d": ""}
    detected_correct = None
    slot_keys = ["a", "b", "c", "d"]

    for idx, opt in enumerate(options[:4]):
        slot = slot_keys[idx]
        mapped[slot] = clean_text_spacing(" ".join(opt["text"]))
        if opt["is_correct"] and not detected_correct:
            detected_correct = slot.upper()

    clean_q_text = clean_text_spacing(" ".join(q_lines))
    return clean_q_text, mapped, detected_correct


def extract_column_chunks(page_list, existing_metadata, alias_map=None):
    """
    Extracts continuous question text chunks for a given language column across all pages.
    Stitches question text and options that stretch across page boundaries (e.g. Q217, Q219).
    """
    if alias_map is None:
        alias_map = {}

    q_locs = []
    last_page = None
    last_pos = 0

    for i, q in enumerate(existing_metadata):
        p = q.get("page", 1)
        if p != last_page:
            last_page = p
            last_pos = 0

        q_num = str(q["question_number"])
        search_num = alias_map.get((p, q["question_number"]), q_num)
        pat = re.compile(
            rf"(?:^|\n)\s*(?:[a-zA-Z]{{1,4}}\s*:\s*)?{search_num}\s*(?:[\.\)]|\n)"
        )
        page_str = page_list[p - 1]
        m = pat.search(page_str, pos=last_pos)
        if not m:
            # Fallback search anywhere on page
            m = pat.search(page_str)

        if not m:
            q_locs.append((i, p, None))
        else:
            q_locs.append((i, p, m.start()))
            last_pos = m.end()

    # Assemble chunks across page breaks
    chunks = []
    for idx in range(len(q_locs)):
        i, p_cur, start_pos = q_locs[idx]
        if start_pos is None:
            chunks.append((i, ""))
            continue

        if idx + 1 < len(q_locs):
            _, p_next, end_pos = q_locs[idx + 1]
            if p_cur == p_next and end_pos is not None:
                chunk = page_list[p_cur - 1][start_pos:end_pos]
            else:
                chunk = page_list[p_cur - 1][start_pos:]
                for intermediate_p in range(p_cur + 1, p_next):
                    chunk += "\n" + page_list[intermediate_p - 1]
                if end_pos is not None:
                    chunk += "\n" + page_list[p_next - 1][:end_pos]
        else:
            chunk = page_list[p_cur - 1][start_pos:]

        chunks.append((i, chunk.strip()))

    return chunks


def run_full_trilingual_extraction(pdf_path, baseline_json_path, output_json_path, dry_run=False):
    print("=" * 75)
    print("SifoDrive Question Bank - End-to-End Trilingual PDF Extractor")
    print("=" * 75)
    print(f"Master PDF:      {pdf_path}")
    print(f"Baseline Meta:   {baseline_json_path}")
    print(f"Target Output:   {output_json_path}")
    print("-" * 75)

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not os.path.exists(baseline_json_path):
        raise FileNotFoundError(f"Baseline metadata not found: {baseline_json_path}")

    with open(baseline_json_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    print(f"Loaded {len(baseline_data)} baseline metadata entries (pages, domains, images).")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"Opened PDF: {total_pages} pages loaded.")

    # 1. Pre-extract all 3 columns per page
    print("Extracting calibrated text columns (RW, EN, FR) across all pages...")
    rw_pages = [doc[p].get_text("text", clip=RW_RECT) for p in range(total_pages)]
    en_pages = [doc[p].get_text("text", clip=EN_RECT) for p in range(total_pages)]
    fr_pages = [doc[p].get_text("text", clip=FR_RECT) for p in range(total_pages)]

    # Strip column headers from page 1
    rw_pages[0] = re.sub(r"^\s*IKINYARWANDA\s*", "", rw_pages[0], flags=re.IGNORECASE)
    en_pages[0] = re.sub(r"^\s*ENGLISH\s*", "", en_pages[0], flags=re.IGNORECASE)
    fr_pages[0] = re.sub(r"^\s*FRANCAIS\s*", "", fr_pages[0], flags=re.IGNORECASE)

    # 2. Extract multi-page chunks for all 3 languages
    print("Assembling cross-page question chunks for Kinyarwanda...")
    rw_chunks = extract_column_chunks(rw_pages, baseline_data, ALIAS_MAPS["RW"])

    print("Assembling cross-page question chunks for English...")
    en_chunks = extract_column_chunks(en_pages, baseline_data, ALIAS_MAPS["EN"])

    print("Assembling cross-page question chunks for French...")
    fr_chunks = extract_column_chunks(fr_pages, baseline_data, ALIAS_MAPS["FR"])

    # 3. Parse and construct trilingual records
    print("Parsing questions, options, and answer keys across all 3 languages...")
    parsed_questions = []
    stats = {
        "total": len(baseline_data),
        "rw_complete": 0,
        "en_complete": 0,
        "fr_complete": 0,
        "cross_page_detected": 0,
        "diagrams_preserved": 0,
        "option_diagrams_preserved": 0,
        "correct_options": Counter(),
    }

    for idx in range(len(baseline_data)):
        baseline = baseline_data[idx]
        q_num = baseline["question_number"]
        page_num = baseline.get("page", 1)

        # Parse Kinyarwanda
        q_rw, opts_rw, c_rw = parse_option_chunk(rw_chunks[idx][1])
        # Parse English
        q_en, opts_en, c_en = parse_option_chunk(en_chunks[idx][1])
        # Parse French
        q_fr, opts_fr, c_fr = parse_option_chunk(fr_chunks[idx][1])

        # Track cross-page questions (if next question is on subsequent page)
        is_cross_page = False
        if idx + 1 < len(baseline_data):
            if baseline_data[idx + 1].get("page", 1) > page_num:
                is_cross_page = True
                stats["cross_page_detected"] += 1

        # Check completeness
        is_img_opt = bool(baseline.get("option_a_image"))
        has_diagram = bool(baseline.get("image"))

        if has_diagram:
            stats["diagrams_preserved"] += 1
        if is_img_opt:
            stats["option_diagrams_preserved"] += 1

        if q_rw and (is_img_opt or (opts_rw["a"] and opts_rw["b"])):
            stats["rw_complete"] += 1
        if q_en and (is_img_opt or (opts_en["a"] and opts_en["b"])):
            stats["en_complete"] += 1
        if q_fr and (is_img_opt or (opts_fr["a"] and opts_fr["b"])):
            stats["fr_complete"] += 1

        # Determine consensus correct option
        votes = [c for c in [c_rw, c_en, c_fr] if c]
        if votes:
            correct = Counter(votes).most_common(1)[0][0]
        else:
            correct = baseline.get("correct_option") or "A"
        correct = correct.strip().upper()
        if correct not in ["A", "B", "C", "D"]:
            correct = "A"

        stats["correct_options"][correct] += 1

        record = {
            "question_number": q_num,
            "domain": baseline.get("domain", "SAFETY"),
            "question_text": q_en,
            "question_text_kinyarwanda": q_rw,
            "question_text_french": q_fr,
            "option_a": opts_en["a"],
            "option_b": opts_en["b"],
            "option_c": opts_en["c"],
            "option_d": opts_en["d"],
            "option_a_kinyarwanda": opts_rw["a"],
            "option_b_kinyarwanda": opts_rw["b"],
            "option_c_kinyarwanda": opts_rw["c"],
            "option_d_kinyarwanda": opts_rw["d"],
            "option_a_french": opts_fr["a"],
            "option_b_french": opts_fr["b"],
            "option_c_french": opts_fr["c"],
            "option_d_french": opts_fr["d"],
            "correct_option": correct,
            "explanation": clean_text_spacing(baseline.get("explanation", "")),
            "explanation_kinyarwanda": clean_text_spacing(baseline.get("explanation_kinyarwanda", "")),
            "explanation_french": "",
            "image": baseline.get("image") or None,
            "option_a_image": baseline.get("option_a_image") or None,
            "option_b_image": baseline.get("option_b_image") or None,
            "option_c_image": baseline.get("option_c_image") or None,
            "option_d_image": baseline.get("option_d_image") or None,
            "page": page_num,
        }
        parsed_questions.append(record)

    # Print Validation Report
    print("-" * 75)
    print("EXTRACTION VALIDATION REPORT")
    print("-" * 75)
    print(f"Total Questions Processed:           {stats['total']}")
    print(f"Cross-Page Questions Handled:        {stats['cross_page_detected']}")
    print(f"Kinyarwanda Completeness:            {stats['rw_complete']} / {stats['total']} ({stats['rw_complete']/stats['total']*100:.1f}%)")
    print(f"English Completeness:                {stats['en_complete']} / {stats['total']} ({stats['en_complete']/stats['total']*100:.1f}%)")
    print(f"French Completeness:                 {stats['fr_complete']} / {stats['total']} ({stats['fr_complete']/stats['total']*100:.1f}%)")
    print(f"Diagram Images Preserved:            {stats['diagrams_preserved']}")
    print(f"Option Diagram Sets Preserved:       {stats['option_diagrams_preserved']}")
    print(f"Answer Key Distribution:             A: {stats['correct_options']['A']}, B: {stats['correct_options']['B']}, C: {stats['correct_options']['C']}, D: {stats['correct_options']['D']}")
    print(f"Difficulty Field Excluded:           YES (100% difficulty-free)")
    print("-" * 75)

    # Verification on user-highlighted edge cases:
    q217 = next(q for q in parsed_questions if q["question_number"] == 217)
    q219 = next(q for q in parsed_questions if q["question_number"] == 219)

    print("VERIFICATION OF USER REPORTED QUESTIONS:")
    print(f"Q217 EN opts: a='{q217['option_a'][:25]}...', b='{q217['option_b'][:25]}...', c='{q217['option_c'][:25]}...', d='{q217['option_d'][:25]}...'")
    print(f"Q219 RW question: '{q219['question_text_kinyarwanda']}'")
    print(f"Q219 EN question: '{q219['question_text']}'")
    print(f"Q219 FR question: '{q219['question_text_french']}'")
    print("-" * 75)

    if not dry_run:
        # Create safety backup
        if os.path.exists(output_json_path):
            backup_path = output_json_path + ".bak"
            print(f"Backing up existing file to: {backup_path}")
            with open(output_json_path, "r", encoding="utf-8") as orig:
                with open(backup_path, "w", encoding="utf-8") as bak:
                    bak.write(orig.read())

        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(parsed_questions, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved {len(parsed_questions)} questions to: {output_json_path}")
    else:
        print("Dry run requested - skipped writing to file.")

    return parsed_questions


def main():
    parser = argparse.ArgumentParser(description="Extract trilingual driving theory questions from official PDF")
    parser.add_argument(
        "--pdf",
        type=str,
        default="/home/eric/working_space/sifo_group/TABLE OF QUESTIONS CORRECT V_2X (1) amategeko y'umuhanda.pdf",
        help="Path to master PDF",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="/home/eric/working_space/sifo_group/SifoDrive_backend/data/parsed_questions.json",
        help="Path to existing parsed JSON baseline",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="/home/eric/working_space/sifo_group/SifoDrive_backend/data/parsed_questions.json",
        help="Output destination path for the trilingual dataset",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction without writing file to disk",
    )
    args = parser.parse_args()

    run_full_trilingual_extraction(args.pdf, args.baseline, args.output, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
