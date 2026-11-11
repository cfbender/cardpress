# Cardpress

Search Scryfall from a browser and print Magic cards and tokens on a thermal
printer. Cardpress runs on the computer the printer is plugged into; you open it
from that computer or from a phone at the table.

A thermal printer has no greys, so Cardpress does not print the card photo. It
typesets the card again in black and white (name, cost, dithered art, type line,
rules text, power/toughness) so the text stays readable.

## Run

Needs [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer.

```sh
uv run cardpress                    # http://127.0.0.1:8765
uv run cardpress --host 0.0.0.0     # also reachable from other devices on your network
```

`--host 0.0.0.0` has no login: anyone on your network can print. Use it on a
network you trust.

To install it as a command and start it at login:

```sh
uv tool install .
mkdir -p ~/.config/systemd/user
cp contrib/cardpress.service ~/.config/systemd/user/
systemctl --user enable --now cardpress
```

## Set up the printer

Cardpress prints on 80 mm ESC/POS receipt printers with a cutter (576 dots
across at 203 DPI). It was written for the Rongta RP820.

Open Settings (the printer button, top right), pick a card size, and enter the
printer address. Settings are saved in `~/.config/cardpress/settings.json`.

| Card size | Result |
| --- | --- |
| Mini card | 72 × 51 mm card printed sideways and cut off; no trimming |
| Full-size card | 63.5 × 89 mm card, cut off; trim the paper either side |

| Printer address | Sends the job |
| --- | --- |
| `tcp://192.168.1.50:9100` | To the printer's Ethernet port (port 9100 if you leave the port off) |
| `/dev/usb/lp0` | Straight to a USB printer through the kernel's `usblp` driver |
| `cups://QueueName` | To a CUPS queue as a raw job (`lp -d QueueName -o raw`) |

Each copy ends with 20 mm of blank paper and a cut. The cutter sits about
15 mm past the print head, so every piece comes out with about 15 mm blank
above the card and 5 mm below it. If your printer cuts into the card or leaves
too much paper below it, change `ESCPOS_FEED_DOTS` in
`src/cardpress/printers.py` (8 dots per mm).

### USB permissions

Writing to `/dev/usb/lp0` usually needs membership of the `lp` group:

```sh
sudo usermod -aG lp "$USER"    # then log out and back in
```

If CUPS has already claimed the printer, `/dev/usb/lp0` may not exist. Use the
`cups://` address instead, or remove the printer from CUPS.

`/dev/usb/lp0` is also missing when the kernel cannot load `usblp`, which
happens after a kernel update until you reboot.

## Search

The search box takes a name or any
[Scryfall search syntax](https://scryfall.com/docs/syntax), such as
`t:zombie pow=2`. "Tokens" also finds emblems and dungeons. Each face of a
double-faced card is listed and printed separately. Only the first page of
results (up to 175 cards) is shown; narrow the search to find the rest.

Cardpress follows Scryfall's [rate limits](https://scryfall.com/docs/api): at
most two searches and ten other requests per second. Card data and images come
from [Scryfall](https://scryfall.com). Cardpress is unofficial fan content, not
approved or endorsed by Wizards of the Coast.

## Develop

```sh
uv run pytest
```

- `src/cardpress/scryfall.py`: Scryfall client; turns cards into printable faces.
- `src/cardpress/render.py`: typesets one face as a 1-bit image.
- `src/cardpress/printers.py`: card sizes, the ESC/POS encoder, delivery.
- `src/cardpress/app.py`: the HTTP API.
- `src/cardpress/static/`: the UI. Plain HTML, CSS, and JavaScript; no build step.

The tests decode the ESC/POS job back to dots with a decoder written from the
command reference, so wrong polarity or row width fails there, not on paper.

## Untested

The full-size card has been printed on an RP820 over USB (`/dev/usb/lp0`).
Not yet tried:

- The 20 mm feed before the cut. It replaces a feed that cut 12 mm into the
  card, and is sized from measurements of that print.
- The mini card on paper.
- `tcp://`, and `cups://` with a real CUPS queue (only checked that `lp` gets
  the right arguments and bytes).
- `contrib/cardpress.service`.

The fonts are DejaVu Sans, bundled under their own licence in
`src/cardpress/fonts/`.
