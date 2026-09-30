"""Pure symbolic playback control; no audio, timing, or transcription."""

import json
from pathlib import Path


class PlaybackError(ValueError):
    """Invalid operation for the current playback state."""


class BoundaryError(PlaybackError):
    """An exit boundary is unknown, misplaced, or not verified."""


class Player:
    def __init__(self, structure):
        lines = structure.get("lines")
        variants = structure.get("pass_variants")
        boundaries = structure.get("exit_boundaries")
        if (not isinstance(lines, list) or len(lines) != 4
                or len(set(lines)) != 4 or not all(isinstance(x, str) for x in lines)):
            raise ValueError("structure requires four distinct line IDs")
        if (not isinstance(variants, list) or len(variants) != 2
                or not all(isinstance(v, dict) for v in variants)
                or [v.get("applies_to") for v in variants] != ["pass_1", "pass_2_and_later"]
                or not all(isinstance(v.get("id"), str) and v["id"] for v in variants)):
            raise ValueError("structure requires first and return variants")
        if not isinstance(boundaries, list):
            raise ValueError("structure requires exit boundaries")
        tomede = structure.get("tomede")
        if (not isinstance(tomede, dict)
                or tomede.get("content_status") not in ("verified", "unverified")
                or tomede.get("entry_status") not in ("verified", "unverified")):
            raise ValueError("structure requires tomede validation status")
        self.lines = tuple(lines)
        self.variants = tuple(v["id"] for v in variants)
        self.boundaries = {}
        for boundary in boundaries:
            if (not isinstance(boundary, dict) or not isinstance(boundary.get("id"), str)
                    or not boundary["id"] or boundary["id"] in self.boundaries
                    or boundary.get("after_line") not in self.lines
                    or boundary.get("validation_status") not in ("verified", "unverified")):
                raise ValueError("invalid exit boundary definition")
            self.boundaries[boundary["id"]] = boundary.copy()
        self.tomede = tomede.copy()
        self.phase = "ready"
        self.pass_number = 0
        self.line_index = 0

    @classmethod
    def from_file(cls, path=None):
        source = Path(path) if path is not None else Path(__file__).with_name("structure.json")
        return cls(json.loads(source.read_text(encoding="utf-8")))

    @property
    def current_line(self):
        return self.lines[self.line_index] if self.phase in ("program", "finish_pending") else None

    @property
    def current_variant(self):
        if self.current_line is None:
            return None
        return self.variants[0] if self.pass_number == 1 else self.variants[1]

    def start(self):
        if self.phase != "ready":
            raise PlaybackError("start requires ready state")
        self.phase = "program"
        self.pass_number = 1

    def request_finish(self):
        if self.phase not in ("program", "finish_pending"):
            raise PlaybackError("finish request requires program state")
        self.phase = "finish_pending"

    def complete_line(self, exit_boundary_id=None):
        if self.phase not in ("program", "finish_pending"):
            raise PlaybackError("line completion requires program state")
        if exit_boundary_id is not None:
            boundary = self.boundaries.get(exit_boundary_id)
            if boundary is None:
                raise BoundaryError("unknown exit boundary")
            if boundary["after_line"] != self.current_line:
                raise BoundaryError("exit boundary is not at the current line")
            if self.line_index != len(self.lines) - 1:
                raise BoundaryError("exit boundary requires the fourth line")
            if boundary["validation_status"] != "verified":
                raise BoundaryError("exit boundary is unverified")
            if self.phase != "finish_pending":
                raise PlaybackError("exit requires a pending finish request")
            if (self.tomede["entry_status"] != "verified"
                    or self.tomede["content_status"] != "verified"):
                raise BoundaryError("tomede is unverified")
            self.phase = "tomede"
            return
        self.line_index += 1
        if self.line_index == len(self.lines):
            self.line_index = 0
            self.pass_number += 1

    def complete_tomede(self):
        if self.phase != "tomede":
            raise PlaybackError("tomede completion requires tomede state")
        self.phase = "ended"
