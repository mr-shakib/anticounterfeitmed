#!/usr/bin/env python
"""Generate the printable label sheet for the physical QR test (docs/11.2).

Produces 20 distinct labels for each size/error-correction combination -- 80
labels in total -- at exact millimetre dimensions on the page, so what comes out
of the printer is the size it claims to be. Print at 100% scale with no fitting
or margins applied by the print dialog, then measure one label with callipers
before trusting the sheet.

The footprint includes the 4-module quiet zone, as the SRS requires. Output goes
to ``out/``, which is git-ignored: these labels carry real-format tokens and must
never be committed.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

import segno

from medcrypto import generate_token, hash_token

HOST = "https://anticounterfeitmed.com"
QUIET_ZONE_MODULES = 4
LABELS_PER_COMBINATION = 20
SIZES_MM = (20, 25)
ERROR_LEVELS = ("M", "Q")

OUT = Path(__file__).parent / "out"


def build_url(token: str) -> str:
    return f"{HOST}/#v=1&t={token}"


def qr_svg(url: str, error: str, footprint_mm: float) -> tuple[str, float, int]:
    """Return an SVG sized to an exact footprint, with its module size in mm."""
    qr = segno.make(url, error=error, boost_error=False)
    modules = qr.symbol_size(scale=1, border=0)[0]
    total_modules = modules + 2 * QUIET_ZONE_MODULES
    module_mm = footprint_mm / total_modules

    buf = io.BytesIO()
    qr.save(
        buf,
        kind="svg",
        border=QUIET_ZONE_MODULES,
        unit="mm",
        scale=module_mm,
        xmldecl=False,
    )
    return buf.getvalue().decode("utf-8"), module_mm, total_modules


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-combination", type=int, default=LABELS_PER_COMBINATION)
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    manifest: list[dict] = []
    sections: list[str] = []

    for size_mm in SIZES_MM:
        for error in ERROR_LEVELS:
            labels_html: list[str] = []
            module_mm = 0.0
            total_modules = 0

            for index in range(1, args.per_combination + 1):
                token = generate_token()
                reference = f"T{size_mm}{error}-{index:03d}"
                svg, module_mm, total_modules = qr_svg(build_url(token), error, size_mm)

                labels_html.append(
                    f'<div class="label">{svg}'
                    f'<div class="ref">{reference}</div></div>'
                )
                manifest.append(
                    {
                        "external_reference": reference,
                        "size_mm": size_mm,
                        "error_correction": error,
                        "module_mm": f"{module_mm:.4f}",
                        "total_modules": total_modules,
                        "token": token,
                        "token_sha256": hash_token(token).hex(),
                    }
                )

            sections.append(
                f"""
  <section>
    <h2>{size_mm}&nbsp;mm &middot; error correction {error}</h2>
    <p class="meta">
      {total_modules} modules across the footprint (including the
      {QUIET_ZONE_MODULES}-module quiet zone) &rarr;
      <strong>{module_mm:.3f}&nbsp;mm per module</strong>.
      {args.per_combination} distinct labels.
    </p>
    <div class="grid">{''.join(labels_html)}</div>
  </section>"""
            )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QR physical test sheet</title>
<style>
  @page {{ size: A4; margin: 10mm; }}
  body {{ font-family: system-ui, sans-serif; color: #000; background: #fff; margin: 0; }}
  h1 {{ font-size: 14pt; margin: 0 0 2mm; }}
  .warn {{ font-size: 9pt; border: 1px solid #000; padding: 2mm; margin-bottom: 4mm; }}
  section {{ page-break-inside: avoid; margin-bottom: 8mm; }}
  h2 {{ font-size: 11pt; margin: 0 0 1mm; }}
  .meta {{ font-size: 8.5pt; margin: 0 0 3mm; color: #333; }}
  .grid {{ display: flex; flex-wrap: wrap; gap: 4mm; }}
  .label {{ text-align: center; }}
  .ref {{ font-family: monospace; font-size: 6pt; margin-top: 0.8mm; }}
  @media print {{ .warn {{ border-color: #000; }} }}
</style>
</head>
<body>
<h1>Physical QR test sheet &mdash; MedSecure PQC</h1>
<div class="warn">
  <strong>Print at 100% scale.</strong> Turn off &ldquo;fit to page&rdquo;,
  &ldquo;shrink oversized pages&rdquo; and any scaling in the print dialog, then
  measure one label with callipers before running the test. Print on the actual
  packaging material. Do not add a logo inside any code.
  These labels carry test tokens only and must never reach production packaging.
</div>
{''.join(sections)}
</body>
</html>
"""

    sheet = OUT / "test-labels.html"
    sheet.write_text(html)

    manifest_path = OUT / "test-labels-manifest.csv"
    with manifest_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0].keys()))
        writer.writeheader()
        writer.writerows(manifest)

    # The results log the testers fill in, one row per trial.
    results_path = OUT / "trial-results-template.csv"
    with results_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "external_reference", "size_mm", "error_correction", "phone_model",
                "lighting", "coated", "decoded", "seconds_to_decode", "notes",
            ]
        )

    print(f"labels:   {len(manifest)}")
    print(f"sheet:    {sheet}")
    print(f"manifest: {manifest_path}  (contains raw test tokens - do not commit)")
    print(f"results:  {results_path}")


if __name__ == "__main__":
    main()
