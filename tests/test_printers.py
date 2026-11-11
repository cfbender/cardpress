"""The print job must decode back to the page that was composed.

The decoder below follows the ESC/POS command reference (GS v 0), not the
encoder, so a flipped polarity or a wrong row width fails here instead of on
paper.
"""

from PIL import Image

from cardpress import printers

MARK = (5, 2)  # one black dot, off-centre so mirrored or shifted output differs


def page_with_mark(size: tuple[int, int]) -> Image.Image:
    page = Image.new("1", size, 1)
    page.putpixel(MARK, 0)
    return page


def black_dots(rows: bytes, row_bytes: int, dot_bit: int) -> set[tuple[int, int]]:
    return {
        (byte_index % row_bytes * 8 + bit, byte_index // row_bytes)
        for byte_index, byte in enumerate(rows)
        for bit in range(8)
        if (byte >> (7 - bit)) & 1 == dot_bit
    }


def test_escpos_job_prints_only_the_marked_dot_then_feeds_and_cuts_after_every_copy():
    job = printers.escpos_job(page_with_mark((576, 300)), copies=2)

    assert job[:2] == b"\x1b@"
    one_copy = job[2 : 2 + (len(job) - 2) // 2]
    assert job[2:] == one_copy * 2

    rows, position = b"", 0
    while one_copy[position : position + 4] == b"\x1dv0\x00":
        row_bytes = int.from_bytes(one_copy[position + 4 : position + 6], "little")
        row_count = int.from_bytes(one_copy[position + 6 : position + 8], "little")
        assert row_bytes == 72 and row_count <= 256
        rows += one_copy[position + 8 : position + 8 + row_bytes * row_count]
        position += 8 + row_bytes * row_count

    # The blank rows after the page carry its end past the cutter, 120 dots from the head.
    assert len(rows) // 72 - 300 == printers.ESCPOS_FEED_DOTS > 120
    assert black_dots(rows, row_bytes=72, dot_bit=1) == {MARK}  # ESC/POS: 1 prints
    assert one_copy[position:] == b"\x1dV\x00"  # cut


def test_sideways_layout_turns_the_card_to_fill_the_paper_width():
    layout = printers.LAYOUTS["mini"]
    card = Image.new("1", layout.card, 1)
    card.putpixel((0, 0), 0)  # top-left corner of the upright card

    page = printers.compose(layout, card)

    assert page.size == (576, 411)
    assert page.getpixel((0, 410)) == 0  # turned a quarter turn: now bottom-left
    assert page.getpixel((0, 0)) != 0
