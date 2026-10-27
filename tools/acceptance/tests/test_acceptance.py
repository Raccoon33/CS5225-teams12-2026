"""Regressions for the five findings in @wkkuu's #67 review.

The gate is the thing that decides whether a deployment passed, so a bug in
it is worse than a bug it fails to catch: it reports success. Each test here
is a case the earlier version accepted.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acceptance import (  # noqa: E402
    REDACTED,
    credential_fields,
    detail_of,
    finite,
    pending_pairs,
    redact,
    station_pinned,
)


class PendingPairs(unittest.TestCase):
    """`resolved` already counts the unavailable pairs."""

    def test_nothing_resolved_leaves_every_pair_pending(self) -> None:
        progress = {"total": 54, "resolved": 2, "unavailable": 2}
        # The old arithmetic subtracted both and reported 50.
        self.assertEqual(pending_pairs(progress), 52)

    def test_all_routes_unavailable_is_zero_pending_not_negative(self) -> None:
        progress = {"total": 54, "resolved": 54, "unavailable": 54}
        # The old arithmetic reported -54.
        self.assertEqual(pending_pairs(progress), 0)

    def test_a_finished_search_has_no_pending_pairs(self) -> None:
        self.assertEqual(pending_pairs({"total": 54, "resolved": 54}), 0)

    def test_an_unusable_progress_block_is_unknown_not_zero(self) -> None:
        self.assertIsNone(pending_pairs(None))
        self.assertIsNone(pending_pairs({"total": "many", "resolved": 1}))
        self.assertIsNone(pending_pairs({"resolved": 1}))


class StationPinned(unittest.TestCase):
    """Checking latitude alone accepted a candidate with no longitude."""

    def station(self, **overrides: object) -> dict[str, object]:
        station = {"stationKey": "KENT_RIDGE", "lat": 1.29455, "lng": 103.78}
        station.update(overrides)
        return {"placeId": "p1", "station": station}

    def test_a_pinned_candidate_passes(self) -> None:
        self.assertTrue(station_pinned(self.station()))

    def test_a_missing_longitude_fails(self) -> None:
        place = self.station()
        del place["station"]["lng"]  # type: ignore[index]
        self.assertFalse(station_pinned(place))

    def test_a_missing_station_key_fails(self) -> None:
        self.assertFalse(station_pinned(self.station(stationKey="")))

    def test_a_zero_coordinate_is_a_coordinate(self) -> None:
        self.assertTrue(station_pinned(self.station(lat=0.0)))

    def test_a_non_numeric_coordinate_fails(self) -> None:
        self.assertFalse(station_pinned(self.station(lng="103.78")))
        self.assertFalse(station_pinned(self.station(lat=float("nan"))))

    def test_no_station_at_all_fails(self) -> None:
        self.assertFalse(station_pinned({"placeId": "p1"}))
        self.assertFalse(station_pinned({"placeId": "p1", "station": None}))
        self.assertFalse(station_pinned("not a place"))

    def test_finite_rejects_booleans(self) -> None:
        self.assertFalse(finite(True))
        self.assertTrue(finite(0))


class Credentials(unittest.TestCase):
    """Two top-level keys were checked; a nested token is just as leaked."""

    def test_a_nested_member_token_is_found(self) -> None:
        body = {"group": {"members": [{"memberId": "m1", "memberToken": "mem_x"}]}}
        self.assertEqual(credential_fields(body), ["group.members[0].memberToken"])

    def test_a_renamed_key_is_still_a_credential(self) -> None:
        self.assertEqual(credential_fields({"member_token": "x"}), ["member_token"])
        self.assertEqual(credential_fields({"Invite-Token": "x"}), ["Invite-Token"])

    def test_a_clean_body_has_none(self) -> None:
        body = {"group": {"members": [{"memberId": "m1", "budget": 1400}]}}
        self.assertEqual(credential_fields(body), [])

    def test_redaction_keeps_the_shape_and_drops_the_value(self) -> None:
        body = {"group": {"members": [{"memberId": "m1", "memberToken": "mem_x"}]}}
        safe = redact(body)
        self.assertEqual(
            safe,
            {"group": {"members": [{"memberId": "m1", "memberToken": REDACTED}]}},
        )
        self.assertNotIn("mem_x", str(safe))

    def test_a_failing_response_does_not_print_its_token(self) -> None:
        """A 500 creation response still carries the tokens it issued."""
        created = {
            "error": {"code": "INTERNAL", "message": "write failed"},
            "memberToken": "mem_secret_value",
            "group": {"inviteToken": "inv_secret_value"},
        }
        detail = detail_of(created, limit=400)
        self.assertNotIn("mem_secret_value", detail)
        self.assertNotIn("inv_secret_value", detail)
        self.assertIn("write failed", detail)

    def test_a_long_detail_is_still_truncated(self) -> None:
        self.assertEqual(len(detail_of({"m": "x" * 500}, limit=40)), 40)


if __name__ == "__main__":
    unittest.main()
