"""Unit tests for turn-by-turn navigation instructions generator."""
from django.test import SimpleTestCase

from navigation.models import Location
from navigation.utils.instructions import (
    _cardinal_direction,
    _turn_description,
    _vector_bearing,
    build_steps,
)


class InstructionsTest(SimpleTestCase):
    def test_vector_bearing(self):
        # East: (0, 0) to (1, 0)
        self.assertAlmostEqual(_vector_bearing(0, 0, 1, 0), 90.0, places=1)
        # North: (0, 0) to (0, 1)
        self.assertAlmostEqual(_vector_bearing(0, 0, 0, 1), 0.0, places=1)
        # South: (0, 0) to (0, -1)
        self.assertAlmostEqual(_vector_bearing(0, 0, 0, -1), 180.0, places=1)
        # West: (0, 0) to (-1, 0)
        self.assertAlmostEqual(_vector_bearing(0, 0, -1, 0), 270.0, places=1)

    def test_cardinal_direction(self):
        self.assertEqual(_cardinal_direction(0.0), "north")
        self.assertEqual(_cardinal_direction(90.0), "east")
        self.assertEqual(_cardinal_direction(180.0), "south")
        self.assertEqual(_cardinal_direction(270.0), "west")

    def test_turn_descriptions(self):
        self.assertEqual(_turn_description(0.0, 10.0), "Continue straight")
        self.assertEqual(_turn_description(0.0, 90.0), "Turn right")
        self.assertEqual(_turn_description(0.0, 270.0), "Turn left")
        self.assertEqual(_turn_description(0.0, 170.0), "Make a sharp right")

    def test_empty_steps(self):
        self.assertEqual(build_steps([]), [])

    def test_single_location_arrival(self):
        loc = Location(id=1, name="Solo Node")
        steps = build_steps([loc])
        self.assertEqual(len(steps), 2)
        self.assertIn("Start at Solo Node", steps[0]["instruction"])
        self.assertIn("already at Solo Node", steps[1]["instruction"])

