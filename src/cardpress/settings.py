"""Printer settings, kept in $XDG_CONFIG_HOME/cardpress/settings.json."""

import os
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator

from .printers import LAYOUTS


class Settings(BaseModel):
    layout: str = "mini"
    # A device file such as /dev/usb/lp0, tcp://host:9100, or cups://queue. Empty until the user sets it.
    target: str = ""

    @field_validator("layout")
    @classmethod
    def _known_layout(cls, key: str) -> str:
        if key not in LAYOUTS:
            raise ValueError(f"unknown layout {key!r}")
        return key

    @field_validator("target")
    @classmethod
    def _stripped(cls, target: str) -> str:
        return target.strip()


def _path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config_home) / "cardpress" / "settings.json"


def load() -> Settings:
    try:
        return Settings.model_validate_json(_path().read_text())
    except (FileNotFoundError, ValidationError):
        return Settings()


def save(settings: Settings) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2) + "\n")
