"""
Generate test artifacts for Playwright comparison
This script creates both HTML and PDF outputs in the test-output directory
Uses CV data for Aline Keller (Phase 1: exact replica of original DOCX)
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from render import render_html, render_pdf
from aline_keller_cv_data import CV_DATA


def main():
    output_dir = Path(__file__).parent / "test-output"
    output_dir.mkdir(exist_ok=True)
    
    print("Generating test artifacts for Aline Keller CV...")

    # Windows-friendly PDF rendering for local tests only.
    os.environ.setdefault("CV_PDF_RENDERER", "playwright")
    
    # Generate HTML
    html_content = render_html(CV_DATA, inline_css=True)
    html_path = output_dir / "preview.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"[OK] HTML saved to: {html_path}")
    
    # Generate PDF
    pdf_bytes = render_pdf(CV_DATA)
    pdf_path = output_dir / "preview.pdf"
    alt_pdf_path = output_dir / "preview.generated.pdf"
    ts_pdf_path = output_dir / f"preview.generated-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    try:
        pdf_path.write_bytes(pdf_bytes)
        print(f"[OK] PDF saved to: {pdf_path}")
    except PermissionError:
        try:
            alt_pdf_path.write_bytes(pdf_bytes)
            print(f"[WARN] preview.pdf is locked; wrote: {alt_pdf_path}")
        except PermissionError:
            ts_pdf_path.write_bytes(pdf_bytes)
            print(f"[WARN] preview.pdf and preview.generated.pdf are locked; wrote: {ts_pdf_path}")
    
    # Also save reference in repo-root samples
    samples_dir = Path(__file__).parent.parent / "samples"
    samples_dir.mkdir(exist_ok=True)
    
    ref_pdf = samples_dir / "reference_output.pdf"
    ref_pdf.write_bytes(pdf_bytes)
    print(f"[OK] Reference PDF saved to: {ref_pdf}")
    
    print("\n[OK] Test artifacts generated successfully!")
    print(f"  HTML: {html_path.relative_to(Path(__file__).parent)}")
    if pdf_path.exists():
        print(f"  PDF:  {pdf_path.relative_to(Path(__file__).parent)}")
    elif alt_pdf_path.exists():
        print(f"  PDF:  {alt_pdf_path.relative_to(Path(__file__).parent)}")
    else:
        print(f"  PDF:  {ts_pdf_path.relative_to(Path(__file__).parent)}")
    print(f"  REF:  {ref_pdf.relative_to(Path(__file__).parent.parent)}")


if __name__ == "__main__":
    main()
