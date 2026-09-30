"""Tests of symbolic control, using a synthetic verified boundary when needed."""

import json
from pathlib import Path
import unittest

from features.gagaku.player import BoundaryError, PlaybackError, Player


STRUCTURE = Path(__file__).with_name("structure.json")


def player_with_verified_exit():
    data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    data["exit_boundaries"][0]["validation_status"] = "verified"  # synthetic test only
    data["tomede"]["entry_status"] = "verified"
    data["tomede"]["content_status"] = "verified"
    return Player(data)


class PlayerTests(unittest.TestCase):
    def test_request_waits_and_repetition_progresses_variants(self):
        player = player_with_verified_exit()
        player.start()
        self.assertEqual((player.current_line, player.current_variant), ("line_1", "first_pass"))
        player.request_finish()
        self.assertEqual(player.phase, "finish_pending")
        for _ in range(4):
            player.complete_line()
        self.assertEqual((player.phase, player.pass_number, player.current_line),
                         ("finish_pending", 2, "line_1"))
        self.assertEqual(player.current_variant, "return_candidate")
        for _ in range(3):
            player.complete_line()
        player.complete_line("after_line_4_candidate")
        self.assertEqual(player.phase, "tomede")
        player.complete_tomede()
        self.assertEqual(player.phase, "ended")

    def test_unrequested_program_repeats(self):
        player = Player.from_file()
        player.start()
        for _ in range(8):
            player.complete_line()
        self.assertEqual((player.phase, player.pass_number, player.current_variant),
                         ("program", 3, "return_candidate"))

    def test_invalid_and_unverified_boundaries_cannot_finish(self):
        player = Player.from_file()
        player.start()
        player.request_finish()
        for _ in range(3):
            player.complete_line()
        for boundary in ("missing", "after_line_4_candidate"):
            with self.subTest(boundary=boundary), self.assertRaises(BoundaryError):
                player.complete_line(boundary)
            self.assertEqual((player.phase, player.current_line), ("finish_pending", "line_4"))

    def test_verified_boundary_still_requires_verified_tomede(self):
        data = json.loads(STRUCTURE.read_text(encoding="utf-8"))
        data["exit_boundaries"][0]["validation_status"] = "verified"
        player = Player(data)
        player.start()
        player.request_finish()
        for _ in range(3):
            player.complete_line()
        with self.assertRaisesRegex(BoundaryError, "tomede is unverified"):
            player.complete_line("after_line_4_candidate")
        self.assertEqual((player.phase, player.current_line), ("finish_pending", "line_4"))

    def test_boundary_at_wrong_line_and_without_request(self):
        player = player_with_verified_exit()
        player.start()
        player.request_finish()
        with self.assertRaisesRegex(BoundaryError, "current line"):
            player.complete_line("after_line_4_candidate")
        self.assertEqual(player.current_line, "line_1")
        other = player_with_verified_exit()
        other.start()
        for _ in range(3):
            other.complete_line()
        with self.assertRaisesRegex(PlaybackError, "pending finish"):
            other.complete_line("after_line_4_candidate")
        self.assertEqual(other.current_line, "line_4")

    def test_invalid_state_operations(self):
        player = Player.from_file()
        with self.assertRaises(PlaybackError):
            player.request_finish()
        with self.assertRaises(PlaybackError):
            player.complete_line()
        with self.assertRaises(PlaybackError):
            player.complete_tomede()
        player.start()
        with self.assertRaises(PlaybackError):
            player.start()


if __name__ == "__main__":
    unittest.main()
