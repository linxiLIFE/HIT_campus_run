import datetime as dt
import unittest
from unittest.mock import patch

import hit_run_simulator as simulator


START_TIME = dt.datetime(2026, 9, 12, 8, 0, tzinfo=dt.timezone.utc)


class RouteGenerationTests(unittest.TestCase):
    def generate(self, campus_key: str, seed: int):
        campus = simulator.CAMPUS_ROUTES[campus_key]
        loop = simulator.track_loop(campus)
        route, timed, _ = simulator.generate_timed_route(
            campus=campus,
            loop=loop,
            target_distance=2200.0,
            target_pace=simulator.parse_pace("5:00"),
            start_time=START_TIME,
            sample_rate=1.0,
            gps_noise=0.0,
            seed=seed,
        )
        return route, timed

    def test_both_campuses_generate_target_distance(self):
        for campus_key in ("campus1", "campus2"):
            with self.subTest(campus=campus_key):
                route, timed = self.generate(campus_key, seed=20260912)
                points = [(lat, lon) for _, lat, lon in timed]
                self.assertGreaterEqual(len(points), 2)
                self.assertAlmostEqual(
                    simulator.gpx_distance(points), 2200.0, delta=1.0
                )
                self.assertGreater(route.start_offset, 0.0)
                self.assertLess(route.start_offset, route.loop_length)

    def test_same_seed_reproduces_route(self):
        first_route, first_timed = self.generate("campus2", seed=12345)
        second_route, second_timed = self.generate("campus2", seed=12345)
        self.assertEqual(first_route, second_route)
        self.assertEqual(first_timed, second_timed)

    def test_different_seed_changes_route(self):
        first_route, first_timed = self.generate("campus2", seed=12345)
        second_route, second_timed = self.generate("campus2", seed=12346)
        self.assertNotEqual(first_route.start_offset, second_route.start_offset)
        self.assertNotEqual(first_timed[0][1:], second_timed[0][1:])

    def test_campus_aliases(self):
        self.assertEqual(simulator.parse_campus("二校区"), "campus2")
        self.assertEqual(simulator.parse_campus("campus-ii"), "campus2")
        self.assertEqual(simulator.parse_campus("1"), "campus1")

    @patch.object(simulator.secrets, "randbits", return_value=987654321)
    def test_missing_seed_uses_system_randomness(self, randbits):
        self.assertEqual(simulator.resolve_seed(None), 987654321)
        randbits.assert_called_once_with(63)
        self.assertEqual(simulator.resolve_seed(42), 42)


if __name__ == "__main__":
    unittest.main()
