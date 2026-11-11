"""Page layouts, the ESC/POS job encoder, and delivery to the printer.

Cardpress prints on 80 mm receipt printers with a cutter: 576 dots across at
203 DPI. A layout says how big the card is and how it sits on the piece of
paper that is cut off.
"""

import socket
import subprocess
import threading
from dataclasses import dataclass

from PIL import Image, ImageOps

PAPER_DOTS = 576  # printable width of 80 mm paper at 203 DPI
ESCPOS_FRAGMENT_ROWS = 256
# Blank lines fed before the cut so the print clears the cutter. Six is what
# python-escpos's cut() sends, the sequence reported working on the Rongta RP820.
ESCPOS_FEED_LINES = 6


@dataclass(frozen=True)
class Layout:
    key: str
    label: str
    description: str
    page: tuple[int, int]  # dots, as fed through the printer
    card: tuple[int, int]  # dots, upright
    sideways: bool = False


LAYOUTS = {
    layout.key: layout
    for layout in (
        Layout(
            "mini",
            "Mini card",
            "72 × 51 mm, printed sideways and cut off. No trimming.",
            page=(PAPER_DOTS, 411),
            card=(411, PAPER_DOTS),
            sideways=True,
        ),
        Layout(
            "full",
            "Full-size card",
            "63.5 × 89 mm, cut off. Trim the paper either side of the border.",
            page=(PAPER_DOTS, 711),
            card=(508, 711),
        ),
    )
}


def compose(layout: Layout, card: Image.Image) -> Image.Image:
    """Place an upright card image on the layout's page."""
    if layout.sideways:
        card = card.rotate(90, expand=True)
    page = Image.new("1", layout.page, 1)
    page.paste(card, ((page.width - card.width) // 2, (page.height - card.height) // 2))
    return page


def escpos_job(page: Image.Image, copies: int) -> bytes:
    """An ESC/POS job printing the page as a raster image, then cutting it off."""
    # GS v 0 prints a dot for every 1 bit: the inverse of Pillow's mode "1".
    # Row padding is 0 after inverting, so it stays blank.
    bits = ImageOps.invert(page.convert("L")).convert("1", dither=Image.Dither.NONE).tobytes()
    row_bytes = -(-page.width // 8)
    fragment_bytes = row_bytes * ESCPOS_FRAGMENT_ROWS

    one_copy = bytearray()
    for start in range(0, len(bits), fragment_bytes):
        fragment = bits[start : start + fragment_bytes]
        rows = len(fragment) // row_bytes
        one_copy += b"\x1dv0\x00" + row_bytes.to_bytes(2, "little") + rows.to_bytes(2, "little") + fragment
    one_copy += b"\x1bd" + bytes([ESCPOS_FEED_LINES])  # ESC d n: feed n lines
    one_copy += b"\x1dV\x00"  # GS V 0: cut

    return b"\x1b@" + bytes(one_copy) * copies  # ESC @: reset the printer first


_printer_lock = threading.Lock()


def send(target: str, data: bytes) -> None:
    """Write a job to tcp://host[:port], a CUPS queue (cups://name), or a device file such as /dev/usb/lp0."""
    with _printer_lock:  # Two jobs interleaved on one printer would garble both.
        if target.startswith("tcp://"):
            host, _, port = target.removeprefix("tcp://").partition(":")
            with socket.create_connection((host, int(port or 9100)), timeout=10) as connection:
                connection.sendall(data)
        elif target.startswith("cups://"):
            # Raw, so CUPS passes our bytes to the queue's backend without running its driver.
            lp = ["lp", "-d", target.removeprefix("cups://"), "-o", "raw"]
            result = subprocess.run(lp, input=data, capture_output=True, timeout=30)
            if result.returncode:
                raise OSError(result.stderr.decode(errors="replace").strip() or "lp failed")
        else:
            with open(target, "wb") as device:
                device.write(data)
