"""Integration tests for Campus Navigation REST APIs and administrative authorization."""
import json
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from navigation.models import Edge, Location

User = get_user_model()


class NavigationAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        Edge.objects.all().delete()
        Location.objects.all().delete()

        self.loc1 = Location.objects.create(name="Gate 1", type="gate", map_x=0.1, map_y=0.1)
        self.loc2 = Location.objects.create(name="Library", type="building", map_x=0.5, map_y=0.5)

        self.edge1 = Edge.objects.create(source=self.loc1, destination=self.loc2, distance=150.0)
        self.edge2 = Edge.objects.create(source=self.loc2, destination=self.loc1, distance=150.0)

        self.admin_user = User.objects.create_superuser(
            username="adminuser", password="adminpassword123", email="admin@campus.edu"
        )
        self.normal_user = User.objects.create_user(
            username="studentuser", password="studentpass123", email="student@campus.edu"
        )

    def test_get_locations(self):
        res = self.client.get("/api/locations/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 2)
        self.assertTrue(any(l["name"] == "Gate 1" for l in data["locations"]))

    def test_location_filtering(self):
        res = self.client.get("/api/locations/?type=building")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["locations"][0]["name"], "Library")

    def test_create_location_unauthorized(self):
        res = self.client.post(
            "/api/locations/",
            data=json.dumps({"name": "Unauthorized Hall"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_create_location_admin(self):
        self.client.force_login(self.admin_user)
        res = self.client.post(
            "/api/locations/",
            data=json.dumps({
                "name": "New Research Block",
                "type": "building",
                "x": 0.7,
                "y": 0.8,
                "description": "Graduate research facility"
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(Location.objects.filter(name="New Research Block").exists())

    def test_find_path_api(self):
        res = self.client.post(
            "/api/find-path/",
            data=json.dumps({
                "source_id": self.loc1.id,
                "destination_id": self.loc2.id,
                "avoid_blocked": True
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["distance"], 150.0)
        self.assertEqual(len(data["steps"]), 2)
        self.assertIn("metrics", data)

    def test_toggle_block_api(self):
        res = self.client.post(
            "/api/toggle-block/",
            data=json.dumps({"edge_id": self.edge1.id, "is_blocked": True}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.edge1.refresh_from_db()
        self.edge2.refresh_from_db()
        self.assertTrue(self.edge1.is_blocked)
        self.assertTrue(self.edge2.is_blocked)

    def test_visualize_api(self):
        res = self.client.post(
            "/api/visualize/",
            data=json.dumps({
                "source_id": self.loc1.id,
                "destination_id": self.loc2.id,
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("trace", data)
        self.assertGreaterEqual(len(data["trace"]), 1)

