"""Unit tests for Dijkstra shortest path algorithm and graph error conditions."""
from django.test import TestCase

from navigation.models import Edge, Location
from navigation.utils.graph import (
    NoPathException,
    build_adjacency,
    dijkstra,
    find_alternative_path,
)


class DijkstraAlgorithmTest(TestCase):
    def setUp(self):
        Edge.objects.all().delete()
        Location.objects.all().delete()

        self.loc_a = Location.objects.create(name="Alpha", map_x=0.1, map_y=0.1)
        self.loc_b = Location.objects.create(name="Beta", map_x=0.5, map_y=0.1)
        self.loc_c = Location.objects.create(name="Gamma", map_x=0.9, map_y=0.1)
        self.loc_d = Location.objects.create(name="Delta", map_x=0.5, map_y=0.9)
        self.loc_isolated = Location.objects.create(name="Isolated", map_x=0.9, map_y=0.9)

        # A <-> B (100m)
        self.e_ab1 = Edge.objects.create(source=self.loc_a, destination=self.loc_b, distance=100.0)
        self.e_ab2 = Edge.objects.create(source=self.loc_b, destination=self.loc_a, distance=100.0)

        # B <-> C (100m)
        self.e_bc1 = Edge.objects.create(source=self.loc_b, destination=self.loc_c, distance=100.0)
        self.e_bc2 = Edge.objects.create(source=self.loc_c, destination=self.loc_b, distance=100.0)

        # A <-> D (50m)
        self.e_ad1 = Edge.objects.create(source=self.loc_a, destination=self.loc_d, distance=50.0)
        self.e_ad2 = Edge.objects.create(source=self.loc_d, destination=self.loc_a, distance=50.0)

        # D <-> C (70m)
        self.e_dc1 = Edge.objects.create(source=self.loc_d, destination=self.loc_c, distance=70.0)
        self.e_dc2 = Edge.objects.create(source=self.loc_c, destination=self.loc_d, distance=70.0)

    def test_direct_path(self):
        result = dijkstra(self.loc_a.id, self.loc_b.id)
        self.assertEqual([loc.id for loc in result.locations], [self.loc_a.id, self.loc_b.id])
        self.assertEqual(result.distance, 100.0)
        self.assertEqual(result.edge_count, 1)

    def test_shortest_weighted_path(self):
        # A -> C: Path via B is 100+100=200m; Path via D is 50+70=120m.
        result = dijkstra(self.loc_a.id, self.loc_c.id)
        self.assertEqual([loc.id for loc in result.locations], [self.loc_a.id, self.loc_d.id, self.loc_c.id])
        self.assertEqual(result.distance, 120.0)
        self.assertEqual(result.edge_count, 2)

    def test_source_equals_destination(self):
        result = dijkstra(self.loc_a.id, self.loc_a.id)
        self.assertEqual([loc.id for loc in result.locations], [self.loc_a.id])
        self.assertEqual(result.distance, 0.0)
        self.assertEqual(result.travel_time, 0.0)
        self.assertEqual(result.edge_count, 0)

    def test_disconnected_node(self):
        with self.assertRaises(NoPathException):
            dijkstra(self.loc_a.id, self.loc_isolated.id)

    def test_invalid_nodes(self):
        with self.assertRaises(ValueError):
            dijkstra(99999, self.loc_a.id)
        with self.assertRaises(ValueError):
            dijkstra(self.loc_a.id, 99999)

    def test_invalid_negative_edge_weight(self):
        Edge.objects.create(source=self.loc_isolated, destination=self.loc_a, distance=-15.0)
        with self.assertRaises(ValueError):
            build_adjacency()

    def test_blocked_edge_and_recalculation(self):
        # Initial shortest route from A to C is via D (120m)
        primary = dijkstra(self.loc_a.id, self.loc_c.id)
        self.assertEqual(primary.distance, 120.0)

        # Block the A <-> D edge
        self.e_ad1.is_blocked = True
        self.e_ad1.save()
        self.e_ad2.is_blocked = True
        self.e_ad2.save()

        # Recalculate: shortest path must now be via B (200m)
        rerouted = dijkstra(self.loc_a.id, self.loc_c.id)
        self.assertEqual([loc.id for loc in rerouted.locations], [self.loc_a.id, self.loc_b.id, self.loc_c.id])
        self.assertEqual(rerouted.distance, 200.0)

    def test_alternative_path(self):
        primary = dijkstra(self.loc_a.id, self.loc_c.id)
        self.assertEqual([loc.id for loc in primary.locations], [self.loc_a.id, self.loc_d.id, self.loc_c.id])

        alt = find_alternative_path(self.loc_a.id, self.loc_c.id, primary)
        self.assertIsNotNone(alt)
        self.assertEqual([loc.id for loc in alt.locations], [self.loc_a.id, self.loc_b.id, self.loc_c.id])
        self.assertEqual(alt.distance, 200.0)

    def test_empty_graph(self):
        Edge.objects.all().delete()
        Location.objects.all().delete()
        with self.assertRaises(ValueError):
            dijkstra(1, 2)

