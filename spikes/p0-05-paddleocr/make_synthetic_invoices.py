"""Generate synthetic invoice images plus their ground truth.

These exist to prove the harness works mechanically — `run_extraction.py`
and `score_accuracy.py` must be exercised end to end *before* any real
client document is involved. Same dry-run-before-live pattern as P0-02,
P0-06 and P0-07.

They are emphatically **not** an accuracy measurement. They are clean,
synthetic, single-layout renderings produced by the same code that writes
the ground truth, so a high score here says the plumbing works and says
nothing whatsoever about PP-StructureV3's accuracy on real invoices. ADR
0008's open item needs 20-50 *real* invoices across vendor formats.

Usage:
    python make_synthetic_invoices.py            # writes samples/
    python make_synthetic_invoices.py --out DIR
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Deliberately three different layouts. A single layout would not exercise
# the one thing PP-Structure is chosen for (ADR 0008: layout analysis and
# table recognition), and would make the harness look more capable than it is.
LAYOUTS = ("classic", "boxed", "compact")

WIDTH, HEIGHT = 1240, 1754  # A4 at ~150 DPI


@dataclass(frozen=True)
class LineItem:
    """One invoice line. Money is Decimal-from-string, per CG5."""

    description: str
    quantity: int
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class Invoice:
    """A synthetic invoice and, by construction, its own ground truth."""

    filename: str
    layout: str
    gstin: str
    vendor_name: str
    invoice_number: str
    invoice_date: str
    line_items: list[LineItem] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((li.amount for li in self.line_items), Decimal("0.00"))

    @property
    def tax_total(self) -> Decimal:
        return (self.subtotal * Decimal("0.18")).quantize(Decimal("0.01"))

    @property
    def grand_total(self) -> Decimal:
        return self.subtotal + self.tax_total


def _specimens() -> list[Invoice]:
    """Three invoices, one per layout, with deliberately varied shapes."""
    return [
        Invoice(
            filename="synthetic_001_classic.png",
            layout="classic",
            gstin="33AABCU9603R1ZX",
            vendor_name="Sundaram Office Supplies Pvt Ltd",
            invoice_number="SOS/2026/0417",
            invoice_date="2026-04-17",
            line_items=[
                LineItem("A4 Copier Paper 75gsm Ream", 20, Decimal("240.00"), Decimal("4800.00")),
                LineItem("Whiteboard Marker Black", 24, Decimal("35.00"), Decimal("840.00")),
                LineItem("Box File Foolscap", 15, Decimal("120.00"), Decimal("1800.00")),
            ],
        ),
        Invoice(
            filename="synthetic_002_boxed.png",
            layout="boxed",
            gstin="27AAGCM1234P1Z5",
            vendor_name="Meridian Logistics Services",
            invoice_number="ML-8842",
            invoice_date="2026-05-02",
            line_items=[
                LineItem("Freight Chennai to Pune", 1, Decimal("18500.00"), Decimal("18500.00")),
                LineItem("Loading and Handling", 2, Decimal("1250.00"), Decimal("2500.00")),
            ],
        ),
        Invoice(
            filename="synthetic_003_compact.png",
            layout="compact",
            gstin="29AACCV7891K1ZB",
            vendor_name="Vayu Technologies",
            invoice_number="VT/INV/2026/331",
            invoice_date="2026-05-19",
            line_items=[
                LineItem("Annual Support Retainer", 1, Decimal("60000.00"), Decimal("60000.00")),
                LineItem("Onsite Visit (per day)", 3, Decimal("4500.00"), Decimal("13500.00")),
                LineItem("Spare Parts Kit", 2, Decimal("2750.00"), Decimal("5500.00")),
                LineItem("Courier Charges", 1, Decimal("450.00"), Decimal("450.00")),
            ],
        ),
    ]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """A real TrueType face; PIL's bitmap default is too small to OCR."""
    names = ["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf", "calibri.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _draw_header(draw: ImageDraw.ImageDraw, inv: Invoice, y: int) -> int:
    """Vendor block and invoice metadata. Returns the next free y."""
    draw.text((60, y), inv.vendor_name, fill="black", font=_font(34, bold=True))
    y += 50
    draw.text((60, y), f"GSTIN: {inv.gstin}", fill="black", font=_font(24))
    y += 38
    draw.text((60, y), "TAX INVOICE", fill="black", font=_font(28, bold=True))
    y += 46
    draw.text((60, y), f"Invoice No: {inv.invoice_number}", fill="black", font=_font(24))
    y += 34
    draw.text((60, y), f"Invoice Date: {inv.invoice_date}", fill="black", font=_font(24))
    return y + 60


def _draw_table(draw: ImageDraw.ImageDraw, inv: Invoice, y: int, boxed: bool) -> int:
    """The line-item table — the part ADR 0008 chose PP-Structure for."""
    cols = (60, 640, 800, 960, 1140)
    head = _font(24, bold=True)
    draw.text((cols[0], y), "Description", fill="black", font=head)
    draw.text((cols[1], y), "Qty", fill="black", font=head)
    draw.text((cols[2], y), "Rate", fill="black", font=head)
    draw.text((cols[3], y), "Amount", fill="black", font=head)
    y += 36
    draw.line((60, y, 1180, y), fill="black", width=2)
    y += 14

    body = _font(23)
    for item in inv.line_items:
        draw.text((cols[0], y), item.description, fill="black", font=body)
        draw.text((cols[1], y), str(item.quantity), fill="black", font=body)
        draw.text((cols[2], y), f"{item.unit_price:,.2f}", fill="black", font=body)
        draw.text((cols[3], y), f"{item.amount:,.2f}", fill="black", font=body)
        if boxed:
            draw.line((60, y + 34, 1180, y + 34), fill="#888888", width=1)
        y += 48
    draw.line((60, y, 1180, y), fill="black", width=2)
    return y + 20


def _draw_totals(draw: ImageDraw.ImageDraw, inv: Invoice, y: int) -> None:
    """Subtotal / GST / grand total, right-aligned-ish."""
    label = _font(24)
    strong = _font(27, bold=True)
    draw.text((800, y), "Subtotal", fill="black", font=label)
    draw.text((990, y), f"{inv.subtotal:,.2f}", fill="black", font=label)
    y += 38
    draw.text((800, y), "IGST 18%", fill="black", font=label)
    draw.text((990, y), f"{inv.tax_total:,.2f}", fill="black", font=label)
    y += 44
    draw.text((800, y), "Total", fill="black", font=strong)
    draw.text((990, y), f"{inv.grand_total:,.2f}", fill="black", font=strong)


def render(inv: Invoice, out_dir: Path) -> Path:
    """Render one invoice to PNG. Layout varies; content does not."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    y = 70 if inv.layout != "compact" else 40
    if inv.layout == "boxed":
        draw.rectangle((40, 40, 1200, 620), outline="black", width=3)
    y = _draw_header(draw, inv, y)
    y = _draw_table(draw, inv, y, boxed=inv.layout == "boxed")
    _draw_totals(draw, inv, y + 20)
    path = out_dir / inv.filename
    image.save(path, dpi=(150, 150))
    return path


def _ground_truth(invoices: list[Invoice]) -> dict[str, object]:
    """Build the ground-truth document in the schema score_accuracy expects."""
    return {
        "schema_version": "1",
        "note": (
            "Synthetic harness fixtures. Generated alongside the images, so these "
            "values are correct by construction — this file measures the pipeline, "
            "not PP-StructureV3's accuracy."
        ),
        "documents": {
            inv.filename: {
                "gstin": inv.gstin,
                "vendor_name": inv.vendor_name,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "subtotal": f"{inv.subtotal:.2f}",
                "tax_total": f"{inv.tax_total:.2f}",
                "grand_total": f"{inv.grand_total:.2f}",
                "line_items": [
                    {
                        "description": li.description,
                        "quantity": str(li.quantity),
                        "unit_price": f"{li.unit_price:.2f}",
                        "amount": f"{li.amount:.2f}",
                    }
                    for li in inv.line_items
                ],
            }
            for inv in invoices
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("samples"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    invoices = _specimens()
    for inv in invoices:
        print(f"  wrote {render(inv, args.out)}  [{inv.layout}]")

    gt_path = args.out / "ground_truth.json"
    gt_path.write_text(
        json.dumps(_ground_truth(invoices), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  wrote {gt_path}  ({len(invoices)} documents)")


if __name__ == "__main__":
    main()
