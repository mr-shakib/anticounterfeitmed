"""What a printed label's QR symbol carries.

A generic scanner must show only the public URL. The package token is carried
in the symbol too, but after the point where every standard decoder stops
reading, so only a reader that asks for the symbol's raw data codewords --
the consumer app and the portal's print-line scanner -- can recover it.

The data codewords of a label symbol, bit by bit::

    0100                      byte mode
    <8-bit count>             len(PUBLIC_URL)
    <PUBLIC_URL, ASCII>       the only text any decoder reports
    0000                      terminator: every standard decoder stops here
                              (the stream is byte-aligned at this point)
    "MV" 0x02                 record marker and format version
    <32 token bytes>          the token, raw rather than Base64url
    EC 11 EC 11 ...           standard padding to the symbol's capacity

The symbol is always version 6 at error correction Q. Fixing it keeps the
printed module size stable for print planning, and it keeps the byte-mode count
field at 8 bits (versions 1-9), which is what the readers expect.

This hides the token from ordinary scanners. It does not make it secret: any
decoder that exposes raw codewords reads it, and a photocopy of the printed
symbol is still a working code. The token stays a possession credential, and
first redemption stays the control.

The encoder here produces data codewords only; drawing the symbol (error
correction, placement, masking) is left to a standard QR library that accepts
raw data codewords. The parser is the reference for the app's and the portal's
parsers, which must agree with it on every file in ``crypto-vectors/label/``.
"""

from __future__ import annotations

import base64

from medcrypto.tokens import TOKEN_BYTES, is_well_formed_token

PUBLIC_URL = "https://anticounterfeitmed.com/"

SYMBOL_VERSION = 6
ERROR_CORRECTION = "Q"
# ISO/IEC 18004 Table 7: version 6 at level Q holds 76 data codewords.
DATA_CODEWORDS = 76

RECORD_MARKER = b"MV"
RECORD_VERSION = 2

_BYTE_MODE = 0b0100
_PAD = (0xEC, 0x11)


class _Bits:
    """Big-endian bit writer, as QR data streams are defined."""

    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, value: int, width: int) -> None:
        self.bits.extend((value >> shift) & 1 for shift in reversed(range(width)))

    def to_bytes(self) -> bytes:
        if len(self.bits) % 8:
            raise ValueError("stream is not byte-aligned")
        return bytes(
            int("".join(map(str, self.bits[i : i + 8])), 2)
            for i in range(0, len(self.bits), 8)
        )


def data_codewords(token: str, *, capacity: int = DATA_CODEWORDS) -> bytes:
    """Return the data codewords of the label symbol for ``token``.

    ``capacity`` exists for the physical print test, which compares error
    correction levels and so needs other symbol sizes. Production labels always
    use the default.
    """
    if not is_well_formed_token(token):
        raise ValueError("malformed token")
    raw_token = base64.urlsafe_b64decode(token + "=")
    # A non-canonical token (stray low bits in its last character) would print
    # as a different token from the one whose digest was stored.
    if base64.urlsafe_b64encode(raw_token).rstrip(b"=").decode("ascii") != token:
        raise ValueError("non-canonical token")

    url = PUBLIC_URL.encode("ascii")
    bits = _Bits()
    bits.put(_BYTE_MODE, 4)
    bits.put(len(url), 8)
    for byte in url:
        bits.put(byte, 8)
    bits.put(0, 4)

    stream = bits.to_bytes() + RECORD_MARKER + bytes([RECORD_VERSION]) + raw_token
    if len(stream) > capacity:
        raise ValueError("label payload does not fit the symbol")
    padding = bytes(_PAD[i % 2] for i in range(capacity - len(stream)))
    return stream + padding


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def take(self, width: int) -> int | None:
        if self.position + width > len(self.data) * 8:
            return None
        value = 0
        for _ in range(width):
            byte = self.data[self.position // 8]
            value = (value << 1) | ((byte >> (7 - self.position % 8)) & 1)
            self.position += 1
        return value


def token_from_data_codewords(raw: bytes, *, text: str | None = None) -> str | None:
    """Return the token a scanned label carries, or None when it is not ours.

    ``raw`` is the symbol's data codewords as a decoder reports them. ``text``
    is the decoder's own reading of the symbol, when it gives one; it must be
    exactly the public URL, so the two readings cannot disagree.

    Strict by design: anything that deviates from the layout above is not one of
    our labels. Bytes after the token are ignored.
    """
    if text is not None and text != PUBLIC_URL:
        return None

    url = PUBLIC_URL.encode("ascii")
    reader = _Reader(raw)
    if reader.take(4) != _BYTE_MODE:
        return None
    if reader.take(8) != len(url):
        return None
    for expected in url:
        if reader.take(8) != expected:
            return None
    if reader.take(4) != 0:
        return None

    record = raw[reader.position // 8 :]
    header = RECORD_MARKER + bytes([RECORD_VERSION])
    if len(record) < len(header) + TOKEN_BYTES or not record.startswith(header):
        return None
    raw_token = record[len(header) : len(header) + TOKEN_BYTES]
    return base64.urlsafe_b64encode(raw_token).rstrip(b"=").decode("ascii")
