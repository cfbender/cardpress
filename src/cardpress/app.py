"""The web service: a JSON API over Scryfall and the printer, plus the static UI."""

import io
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from . import printers, scryfall, settings
from .render import render_card

app = FastAPI(title="Cardpress")


@app.exception_handler(scryfall.ScryfallError)
def scryfall_error(_request, error: scryfall.ScryfallError) -> JSONResponse:
    # Pass "not found" and "bad query" through; anything else is Scryfall's problem, not the caller's.
    status = error.status if error.status in (400, 404, 422) else 502
    return JSONResponse({"detail": error.details}, status_code=status)


def _page(card_id: UUID, face_index: int, layout: printers.Layout) -> Image.Image:
    faces = scryfall.card_faces(str(card_id))
    if face_index >= len(faces):
        raise HTTPException(404, "That card has no such face.")
    face = faces[face_index]
    art = Image.open(io.BytesIO(scryfall.art(face.art_url))) if face.art_url else None
    return printers.compose(layout, render_card(face, art, *layout.card))


@app.get("/api/search")
def search(q: str, kind: Literal["tokens", "cards", "all"] = "tokens") -> dict:
    query = q.strip()
    result = scryfall.search(query, kind)
    # Scryfall sorts by name, which puts "Artifact Zombie" ahead of "Zombie". Lead with exact names.
    faces = sorted(result.faces, key=lambda face: face.name.casefold() != query.casefold())
    return {
        "results": [asdict(face) for face in faces],
        "total_cards": result.total_cards,
        "has_more": result.has_more,
    }


@app.get("/api/preview.png")
def preview(id: UUID, face: int = Query(0, ge=0), layout: str | None = None) -> Response:
    """The exact 1-bit page that printing would send, as a PNG."""
    chosen = printers.LAYOUTS.get(layout or settings.load().layout)
    if chosen is None:
        raise HTTPException(404, f"Unknown layout {layout!r}.")
    png = io.BytesIO()
    _page(id, face, chosen).save(png, "PNG")
    return Response(png.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


class PrintRequest(BaseModel):
    id: UUID
    face: int = Field(0, ge=0)
    copies: int = Field(1, ge=1, le=20)


@app.post("/api/print")
def print_card(request: PrintRequest) -> dict:
    current = settings.load()
    if not current.target:
        raise HTTPException(409, "No printer is set. Choose one in Settings.")
    layout = printers.LAYOUTS[current.layout]
    data = printers.escpos_job(_page(request.id, request.face, layout), request.copies)
    try:
        printers.send(current.target, data)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise HTTPException(502, f"Could not print to {current.target}: {error}") from error
    return {"copies": request.copies}


def _settings_body(current: settings.Settings) -> dict:
    layouts = [
        {"key": layout.key, "label": layout.label, "description": layout.description}
        for layout in printers.LAYOUTS.values()
    ]
    return {**current.model_dump(), "layouts": layouts}


@app.get("/api/settings")
def get_settings() -> dict:
    return _settings_body(settings.load())


@app.put("/api/settings")
def put_settings(new: settings.Settings) -> dict:
    settings.save(new)
    return _settings_body(new)


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
