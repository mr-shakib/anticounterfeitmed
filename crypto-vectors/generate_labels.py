#!/usr/bin/env python
"""Regenerate the label-symbol vectors in ``label/``.

Kept apart from generate.py because nothing here is random: these files are
fully determined by the layout in medcrypto/labels.py, and regenerating them
must not re-sign the signature vectors.

Each vector is a symbol's data codewords as a decoder reports them, plus the
text reading that decoder gave. The Python reference, the Dart app and the
portal must all reach the vector's verdict -- and, for a valid one, its token.

Two images of the valid label go alongside, for the readers that start from a
picture rather than from codewords: the clean symbol, and a camera-like frame
-- the label small in a 1280x720 view, slightly rotated, saved as JPEG at
quality 50, which is what mobile_scanner hands the app.
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from PIL import Image
from qrcodegen import QrCode

from medcrypto import labels

HERE = Path(__file__).parent
FOLDER = HERE / "label"

TOKEN_BYTES = bytes((i * 7 + 11) % 256 for i in range(32))
TOKEN = base64.urlsafe_b64encode(TOKEN_BYTES).rstrip(b"=").decode()


def stream(
    *,
    url: bytes = labels.PUBLIC_URL.encode("ascii"),
    mode: int = 0b0100,
    terminator: int = 0,
    record: bytes | None = b"MV\x02" + TOKEN_BYTES,
) -> bytes:
    """Build data codewords by hand, so a vector can break one rule at a time."""
    bits: list[int] = []

    def put(value: int, width: int) -> None:
        bits.extend((value >> s) & 1 for s in reversed(range(width)))

    put(mode, 4)
    put(len(url), 8)
    for byte in url:
        put(byte, 8)
    put(terminator, 4)
    while len(bits) % 8:
        bits.append(0)
    head = bytes(int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8))
    body = head + (record or b"")
    return body + bytes((0xEC, 0x11)[i % 2] for i in range(labels.DATA_CODEWORDS - len(body)))


def write(name: str, description: str, data: bytes, expected: str, *,
          text: str | None = labels.PUBLIC_URL) -> None:
    vector = {
        "name": name,
        "description": description,
        "check": "label",
        "data_codewords": data.hex(),
        "text": text,
        "expected": expected,
    }
    if expected == "VALID":
        vector["token"] = TOKEN
    (FOLDER / f"{name}.json").write_text(json.dumps(vector, indent=2) + "\n")


def main() -> None:
    shutil.rmtree(FOLDER, ignore_errors=True)
    FOLDER.mkdir()

    reference = labels.data_codewords(TOKEN)
    assert stream() == reference, "hand-built stream drifted from the encoder"

    write("valid-label", "A label symbol exactly as the encoder produces it.",
          reference, "VALID")
    write("valid-label-no-text",
          "The same symbol from a decoder that reports raw codewords only.",
          reference, "VALID", text=None)

    write("public-url-only",
          "A code re-made from what an ordinary scanner shows: the public URL, "
          "padding, no record.",
          stream(record=None), "INVALID")
    write("wrong-marker", "Record marker is not 'MV'.",
          stream(record=b"MX\x02" + TOKEN_BYTES), "INVALID")
    write("wrong-record-version", "Record format version is not 2.",
          stream(record=b"MV\x03" + TOKEN_BYTES), "INVALID")
    write("truncated-record",
          "The codewords end partway through the token.",
          stream()[: (4 + 8 + 8 * len(labels.PUBLIC_URL) + 4) // 8 + 3 + 16],
          "INVALID")
    write("text-disagrees",
          "Valid codewords, but the decoder's text reading is something else.",
          reference, "INVALID", text="https://anticounterfeitmed.com/#v=1")
    write("look-alike-host",
          "A same-length look-alike URL carrying a well-formed record.",
          stream(url=b"https://anticounterfeitmeb.com/"), "INVALID",
          text="https://anticounterfeitmeb.com/")
    write("longer-url",
          "Our URL with a path appended, carrying a well-formed record.",
          stream(url=b"https://anticounterfeitmed.com/x"), "INVALID",
          text="https://anticounterfeitmed.com/x")
    write("not-byte-mode", "The first segment is not in byte mode.",
          stream(mode=0b0010), "INVALID", text=None)
    write("no-terminator",
          "The URL is followed by another segment rather than the terminator.",
          stream(terminator=0b0100), "INVALID", text=None)

    write_images(reference)
    print(f"wrote {len(list(FOLDER.glob('*.json')))} label vectors and 2 images")


def write_images(data: bytes) -> None:
    symbol = QrCode(labels.SYMBOL_VERSION, QrCode.Ecc.QUARTILE, list(data), -1)
    side = symbol.get_size() + 8
    clean = Image.new("L", (side, side), 255)
    for y in range(symbol.get_size()):
        for x in range(symbol.get_size()):
            if symbol.get_module(x, y):
                clean.putpixel((x + 4, y + 4), 0)
    clean.resize((side * 8, side * 8), Image.NEAREST).save(
        FOLDER / "valid-label.png", optimize=True
    )

    # About 5 px per module: a 20 mm label held at a comfortable distance.
    label = clean.resize((side * 5, side * 5), Image.NEAREST).rotate(
        7, resample=Image.BILINEAR, expand=True, fillcolor=255
    )
    frame = Image.new("L", (1280, 720), 205)
    frame.paste(label, (520, 180))
    frame.convert("RGB").save(FOLDER / "valid-label-frame.jpg", quality=50)


if __name__ == "__main__":
    main()
