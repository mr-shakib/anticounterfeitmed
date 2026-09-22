"""The printed label symbol.

What these hold: an ordinary scanner reads only the public URL from a label,
while our own readers recover the token from the same printed symbol. The
generic side is checked with ZXing, an independent decoder that many scanner
apps are built on -- not with our own parser, which would only agree with
itself.
"""

from __future__ import annotations

import base64

import pytest
import zxingcpp
from PIL import Image
from qrcodegen import QrCode, QrSegment

from medcrypto import generate_token, hash_token
from medcrypto import labels

_ECC = {"Q": QrCode.Ecc.QUARTILE}


def draw(data_codewords: bytes, scale: int = 8, border: int = 4) -> Image.Image:
    """Render the symbol as the portal does: from raw data codewords."""
    symbol = QrCode(
        labels.SYMBOL_VERSION,
        _ECC[labels.ERROR_CORRECTION],
        list(data_codewords),
        -1,
    )
    return raster(symbol, scale, border)


def raster(symbol: QrCode, scale: int = 8, border: int = 4) -> Image.Image:
    size = symbol.get_size()
    side = (size + 2 * border) * scale
    image = Image.new("L", (side, side), 255)
    for y in range(size):
        for x in range(size):
            if symbol.get_module(x, y):
                left, top = (x + border) * scale, (y + border) * scale
                image.paste(0, (left, top, left + scale, top + scale))
    return image


def test_capacity_matches_the_standard():
    assert labels.DATA_CODEWORDS == QrCode._get_num_data_codewords(
        labels.SYMBOL_VERSION, _ECC[labels.ERROR_CORRECTION]
    )


def test_a_generic_scanner_reads_only_the_public_url():
    token = generate_token()
    results = zxingcpp.read_barcodes(draw(labels.data_codewords(token)))

    assert len(results) == 1
    assert results[0].text == labels.PUBLIC_URL
    assert results[0].bytes == labels.PUBLIC_URL.encode("ascii")
    assert token not in results[0].text


def test_our_reader_recovers_the_token():
    token = generate_token()
    codewords = labels.data_codewords(token)

    recovered = labels.token_from_data_codewords(codewords, text=labels.PUBLIC_URL)
    assert recovered == token
    # The stored digest is over the token text, so hiding the token in raw
    # form changes nothing about what the credential commits to.
    assert hash_token(recovered) == hash_token(token)


def test_the_layout_is_exactly_as_documented():
    token = generate_token()
    codewords = labels.data_codewords(token)
    url = labels.PUBLIC_URL.encode("ascii")

    assert len(codewords) == labels.DATA_CODEWORDS
    # Byte mode, count 31, then the URL shifted by the 12-bit header.
    assert codewords[0] == 0x40 | (len(url) >> 4)
    assert codewords[1] == ((len(url) & 0x0F) << 4) | (url[0] >> 4)
    # Header, URL and terminator end exactly on a byte boundary.
    record_at = (4 + 8 + 8 * len(url) + 4) // 8
    assert codewords[record_at - 1] & 0x0F == 0, "terminator"
    record = codewords[record_at:]
    assert record[:3] == b"MV\x02"
    assert record[3:35] == base64.urlsafe_b64decode(token + "=")
    assert set(record[35:]) <= {0xEC, 0x11}


def test_a_code_made_from_the_public_reading_is_not_ours():
    """What someone gets by re-encoding what their scanner showed them."""
    remade = QrCode.encode_segments(
        [QrSegment.make_bytes(labels.PUBLIC_URL.encode("ascii"))],
        QrCode.Ecc.QUARTILE,
        minversion=labels.SYMBOL_VERSION,
        maxversion=labels.SYMBOL_VERSION,
        boostecl=False,
    )
    results = zxingcpp.read_barcodes(raster(remade))
    assert results[0].text == labels.PUBLIC_URL

    # The same text, but no record after the terminator.
    codewords = labels.data_codewords(generate_token())
    record_at = (4 + 8 + 8 * len(labels.PUBLIC_URL) + 4) // 8
    padded_only = codewords[:record_at] + bytes(
        (0xEC, 0x11)[i % 2] for i in range(labels.DATA_CODEWORDS - record_at)
    )
    assert labels.token_from_data_codewords(padded_only) is None


@pytest.mark.parametrize(
    "text",
    [
        "https://anticounterfeitmed.com",
        "https://anticounterfeitmed.com/#v=1",
        "",
    ],
)
def test_a_disagreeing_text_reading_is_refused(text):
    codewords = labels.data_codewords(generate_token())
    assert labels.token_from_data_codewords(codewords, text=text) is None


@pytest.mark.parametrize(
    "token",
    [
        "short",
        "!" * 43,
        # 43 legal characters whose last one carries bits a 32-byte value
        # cannot have: it would print as a different token.
        "A" * 42 + "B",
    ],
)
def test_the_encoder_refuses_a_token_it_cannot_carry_faithfully(token):
    with pytest.raises(ValueError):
        labels.data_codewords(token)
