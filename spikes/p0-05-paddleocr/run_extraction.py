"""Run PP-StructureV3 over a folder of invoices and emit structured JSON.

One JSON file per input document, written to --out. Works against ANY
folder of invoices — synthetic fixtures, public samples, or (once they
exist) a gitignored real-samples/ directory. Nothing here is hardcoded to
the practice's data.

Per ADR 0008 this is CPU-only. The module prints the CUDA-compiled flag on
startup so a GPU build cannot be used by accident and reported as if it
were the ADR's configuration.

Field extraction is deliberately simple heuristics over PP-StructureV3's
output, not a trained extractor. That is the point: the spike measures
what PP-StructureV3 *gives* you, and a heuristic layer thin enough to see
through. A miss should be attributable to OCR or to layout analysis, not
buried in a clever parser — so when a field fails here, the FINDINGS entry
has to say which of the two it was.

Usage:
    python run_extraction.py --input samples/ --out out/
    python run_extraction.py --input real-samples/ --out real-results/
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".pdf"})

# 2 digits (state) + 5 letters + 4 digits + 1 letter + 1 alnum + Z + 1 alnum.
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z])\b")
AMOUNT_RE = re.compile(r"-?[\d,]+\.\d{2}|\b\d{1,3}(?:,\d{2,3})+\b")
DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)
INVOICE_NO_RE = re.compile(r"invoice\s*(?:no|number|#)\.?\s*[:\-]?\s*(\S+)", re.IGNORECASE)

# Lines that are never a vendor name, however near the top they sit.
_NOT_VENDOR = re.compile(
    r"^(tax\s+invoice|invoice|bill\s+of\s+supply|gstin|original|duplicate|"
    r"credit\s+note|debit\s+note|proforma)\b",
    re.IGNORECASE,
)


def _load_pipeline() -> Any:
    """Construct PP-StructureV3 once; it is expensive to build.

    Formula, chart and seal recognition are switched off. They are not
    free: PP-FormulaNet_plus-L alone is a multi-hundred-MB download that
    loads on every construction, and an invoice contains no LaTeX. Table
    recognition stays on — it is the capability ADR 0008 chose this engine
    for, and turning it off would make the spike measure the wrong thing.

    Orientation classification and unwarping are also off, for speed on
    born-digital inputs. Scanned or photographed invoices may well need
    them; that is an open question in FINDINGS.md rather than a setting to
    guess at now.
    """
    import paddle
    from paddleocr import PPStructureV3

    print(f"  paddle {paddle.__version__}  compiled_with_cuda="
          f"{paddle.is_compiled_with_cuda()}  (ADR 0008: CPU-only)")
    return PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_formula_recognition=False,
        use_chart_recognition=False,
        use_seal_recognition=False,
        use_table_recognition=True,
    )


def _unwrap(result: Any) -> dict[str, Any]:
    """PP-StructureV3 wraps its payload under 'res' in some versions."""
    payload = result.json if hasattr(result, "json") else result
    if isinstance(payload, dict) and "res" in payload and isinstance(payload["res"], dict):
        return payload["res"]
    return payload if isinstance(payload, dict) else {}


def _text_boxes(res: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten OCR output to [{text, x0, y0, x1, y1}], sorted top-to-bottom."""
    ocr = res.get("overall_ocr_res") or res
    texts = ocr.get("rec_texts") or []
    boxes = ocr.get("rec_boxes")
    if boxes is None or len(boxes) == 0:
        boxes = ocr.get("dt_polys") or []
    out: list[dict[str, Any]] = []
    for idx, text in enumerate(texts):
        if idx >= len(boxes):
            break
        pts = boxes[idx]
        flat = [float(v) for p in pts for v in (p if hasattr(p, "__len__") else [p])]
        xs, ys = flat[0::2], flat[1::2]
        if not xs or not ys:
            continue
        out.append({"text": str(text).strip(), "x0": min(xs), "y0": min(ys),
                    "x1": max(xs), "y1": max(ys)})
    return sorted(out, key=lambda b: (b["y0"], b["x0"]))


def _value_right_of(boxes: list[dict[str, Any]], label: dict[str, Any]) -> str | None:
    """The nearest box to the right on the same visual row.

    Totals blocks put the label and the figure in separate OCR boxes, so a
    line-by-line regex finds the word 'Subtotal' and no number. Pairing by
    geometry is what makes them recoverable.
    """
    mid = (label["y0"] + label["y1"]) / 2
    height = max(label["y1"] - label["y0"], 1.0)
    candidates = [
        b for b in boxes
        if b is not label
        and b["x0"] >= label["x1"] - 2
        and abs((b["y0"] + b["y1"]) / 2 - mid) < height * 0.8
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda b: b["x0"])["text"]


def _find_labelled(boxes: list[dict[str, Any]], pattern: re.Pattern[str]) -> str | None:
    """Value for a label: same-box text after the colon, else the box right."""
    for box in boxes:
        if not pattern.search(box["text"]):
            continue
        tail = box["text"].split(":", 1)[1].strip() if ":" in box["text"] else ""
        if tail:
            return tail
        neighbour = _value_right_of(boxes, box)
        if neighbour:
            return neighbour
    return None


def _first_amount(text: str | None) -> str | None:
    if not text:
        return None
    match = AMOUNT_RE.search(text)
    return match.group(0).replace(",", "") if match else None


def _extract_totals(boxes: list[dict[str, Any]]) -> dict[str, str | None]:
    """Subtotal / tax / grand total, by label then geometry."""
    subtotal = _find_labelled(boxes, re.compile(r"\bsub\s*-?\s*total\b", re.IGNORECASE))
    tax = _find_labelled(boxes, re.compile(r"\b(igst|cgst|sgst|gst|tax)\b", re.IGNORECASE))
    grand = _find_labelled(
        boxes, re.compile(r"\b(grand\s+total|total\s+amount|net\s+payable|total)\b", re.IGNORECASE)
    )
    return {
        "subtotal": _first_amount(subtotal),
        "tax_total": _first_amount(tax),
        "grand_total": _first_amount(grand),
    }


def _extract_vendor(boxes: list[dict[str, Any]]) -> str | None:
    """Tallest text in the top third that is not a document-type heading."""
    if not boxes:
        return None
    page_top = min(b["y0"] for b in boxes)
    page_bottom = max(b["y1"] for b in boxes)
    cutoff = page_top + (page_bottom - page_top) * 0.33
    candidates = [
        b for b in boxes
        if b["y0"] <= cutoff and b["text"] and not _NOT_VENDOR.match(b["text"])
        and not GSTIN_RE.search(b["text"])
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda b: b["y1"] - b["y0"])["text"]


def _extract_fields(boxes: list[dict[str, Any]]) -> dict[str, str | None]:
    """The scalar fields ADR 0008 names: GSTIN, vendor, amounts, dates."""
    joined = "\n".join(b["text"] for b in boxes)
    gstin_match = GSTIN_RE.search(joined.upper().replace(" ", ""))
    inv_no = _find_labelled(boxes, INVOICE_NO_RE)
    if inv_no:
        tail = INVOICE_NO_RE.search(inv_no)
        inv_no = tail.group(1) if tail else inv_no
    date_text = _find_labelled(boxes, re.compile(r"invoice\s*date|\bdate\b", re.IGNORECASE))
    date_match = DATE_RE.search(date_text or "") or DATE_RE.search(joined)
    fields: dict[str, str | None] = {
        "gstin": gstin_match.group(1) if gstin_match else None,
        "vendor_name": _extract_vendor(boxes),
        "invoice_number": inv_no,
        "invoice_date": date_match.group(1) if date_match else None,
    }
    fields.update(_extract_totals(boxes))
    return fields


def _html_rows(html: str) -> list[list[str]]:
    """Parse a table's HTML into rows of cell text."""
    rows: list[list[str]] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", html, flags=re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.DOTALL | re.IGNORECASE)
        rows.append([re.sub(r"<[^>]+>", "", c).strip() for c in cells])
    return rows


def _row_to_item(cells: list[str]) -> dict[str, str] | None:
    """A line item is a row whose last cell is an amount and first is text."""
    if len(cells) < 2 or not cells[0]:
        return None
    amount = _first_amount(cells[-1])
    if amount is None:
        return None
    if re.match(r"^\s*(sub\s*-?total|total|grand|igst|cgst|sgst|tax)\b", cells[0], re.IGNORECASE):
        return None
    numeric = [c for c in cells[1:-1] if _first_amount(c) or c.strip().isdigit()]
    return {
        "description": cells[0],
        "quantity": numeric[0].strip() if numeric else None,
        "unit_price": _first_amount(numeric[-1]) if len(numeric) > 1 else None,
        "amount": amount,
    }


def _extract_line_items(res: dict[str, Any]) -> list[dict[str, Any]]:
    """Line items from PP-Structure's recognised tables.

    This is the capability ADR 0008 chose PaddleOCR *for* — DocTR was
    rejected over exactly this. If table recognition underperforms on real
    invoices, that is a finding about the ADR, not about this parser.
    """
    items: list[dict[str, Any]] = []
    for table in res.get("table_res_list") or []:
        html = table.get("pred_html") or ""
        for cells in _html_rows(html):
            item = _row_to_item(cells)
            if item:
                items.append(item)
    return items


def extract_document(pipeline: Any, path: Path) -> dict[str, Any]:
    """Run one document through the pipeline and shape the result."""
    started = time.monotonic()
    results = list(pipeline.predict(input=str(path)))
    elapsed_ms = (time.monotonic() - started) * 1000
    boxes: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    tables: list[list[list[str]]] = []
    for result in results:
        res = _unwrap(result)
        boxes.extend(_text_boxes(res))
        items.extend(_extract_line_items(res))
        tables.extend(_html_rows(t.get("pred_html") or "")
                      for t in res.get("table_res_list") or [])
    return {
        "source_file": path.name,
        "engine": "PP-StructureV3",
        "elapsed_ms": round(elapsed_ms, 1),
        "pages": len(results),
        "tables_detected": len(tables),
        "fields": _extract_fields(boxes),
        "line_items": items,
        # Kept deliberately: when zero line items come back, this is what
        # distinguishes "table recognition failed" from "the row parser
        # rejected good rows". Without it a failure is unattributable, and
        # an unattributable failure cannot become a finding.
        "table_rows_raw": tables,
        "raw_text_lines": [b["text"] for b in boxes],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PP-StructureV3 over a folder of invoices.")
    parser.add_argument("--input", type=Path, required=True, help="folder of invoices")
    parser.add_argument("--out", type=Path, required=True, help="output folder for JSON")
    args = parser.parse_args()

    documents = sorted(
        p for p in args.input.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not documents:
        print(f"  no invoices found in {args.input}")
        return
    args.out.mkdir(parents=True, exist_ok=True)

    pipeline = _load_pipeline()
    total_ms = 0.0
    for path in documents:
        record = extract_document(pipeline, path)
        total_ms += record["elapsed_ms"]
        (args.out / f"{path.stem}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        found = sum(1 for v in record["fields"].values() if v)
        print(f"  {path.name:<34} {record['elapsed_ms']:>8.0f}ms  "
              f"fields {found}/7  items {len(record['line_items'])}  "
              f"tables {record['tables_detected']}")
    print(f"\n  {len(documents)} documents in {total_ms / 1000:.1f}s "
          f"({total_ms / len(documents) / 1000:.1f}s each, CPU) -> {args.out}")


if __name__ == "__main__":
    main()
