"""Tests for campus map upload, validation, multi-map management, and API endpoints."""
from __future__ import annotations

import io
import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from navigation.models import CampusMap, Edge, Location
from navigation.utils.map_parser import (
    generate_template_csv,
    generate_template_json,
    generate_template_xlsx,
    parse_and_validate_map_data,
)


# ---------------------------------------------------------------------------
# Map Parser Unit Tests
# ---------------------------------------------------------------------------


class TestMapParserJSON(TestCase):
    """Unit tests for JSON campus map parsing and validation."""

    def _valid_json(self, extra=None):
        data = {
            "map_name": "Test Campus",
            "locations": [
                {"name": "Gate A", "type": "gate", "map_x": 0.1, "map_y": 0.2},
                {"name": "Library", "type": "building", "map_x": 0.5, "map_y": 0.5},
                {"name": "Cafeteria", "type": "facility", "map_x": 0.8, "map_y": 0.6},
            ],
            "edges": [
                {"source": "Gate A", "destination": "Library", "distance": 120.0},
                {"source": "Library", "destination": "Cafeteria", "distance": 80.0},
            ],
        }
        if extra:
            data.update(extra)
        return json.dumps(data).encode("utf-8")

    def test_valid_json_parses_successfully(self):
        payload, errors, warnings = parse_and_validate_map_data(self._valid_json(), "test.json")
        self.assertIsNotNone(payload)
        self.assertEqual(errors, [])
        self.assertEqual(payload["map_name"], "Test Campus")
        self.assertEqual(len(payload["locations"]), 3)
        self.assertEqual(len(payload["edges"]), 2)

    def test_negative_distance_is_rejected(self):
        data = json.loads(self._valid_json())
        data["edges"][0]["distance"] = -50.0
        payload, errors, warnings = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        self.assertIsNone(payload)
        self.assertTrue(any("non-positive" in e or "distance" in e.lower() for e in errors))

    def test_zero_distance_is_rejected(self):
        data = json.loads(self._valid_json())
        data["edges"][0]["distance"] = 0.0
        payload, errors, _ = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        self.assertIsNone(payload)

    def test_dangling_edge_reference_is_rejected(self):
        data = json.loads(self._valid_json())
        data["edges"].append({"source": "Gate A", "destination": "NonExistentBuilding", "distance": 50.0})
        payload, errors, _ = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        self.assertIsNone(payload)
        self.assertTrue(any("NonExistentBuilding" in e for e in errors))

    def test_self_loop_edges_produce_warning(self):
        data = json.loads(self._valid_json())
        data["edges"].append({"source": "Gate A", "destination": "Gate A", "distance": 10.0})
        payload, errors, warnings = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        # Self-loop should produce a warning and be skipped, not an error
        self.assertTrue(any("self" in w.lower() or "loop" in w.lower() for w in warnings))

    def test_empty_locations_produces_error(self):
        data = {"map_name": "Empty", "locations": [], "edges": []}
        payload, errors, _ = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "empty.json"
        )
        self.assertIsNone(payload)
        self.assertTrue(len(errors) > 0)

    def test_duplicate_location_name_produces_warning(self):
        data = json.loads(self._valid_json())
        data["locations"].append({"name": "Gate A", "type": "gate", "map_x": 0.9, "map_y": 0.1})
        payload, errors, warnings = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        self.assertTrue(any("Duplicate" in w for w in warnings))

    def test_map_x_clamped_to_valid_range(self):
        data = json.loads(self._valid_json())
        data["locations"][0]["map_x"] = 2.5  # Out of [0, 1]
        data["locations"][0]["map_y"] = -0.3
        payload, errors, _ = parse_and_validate_map_data(
            json.dumps(data).encode("utf-8"), "test.json"
        )
        # Should clamp, not error
        self.assertIsNotNone(payload)
        gate = next(l for l in payload["locations"] if l["name"] == "Gate A")
        self.assertEqual(gate["map_x"], 1.0)
        self.assertEqual(gate["map_y"], 0.0)

    def test_unsupported_format_returns_error(self):
        payload, errors, _ = parse_and_validate_map_data(b"data", "test.txt")
        self.assertIsNone(payload)
        self.assertTrue(any("Unsupported" in e for e in errors))


class TestMapParserCSV(TestCase):
    """Unit tests for CSV campus map parsing."""

    def _valid_csv(self):
        return (
            "[locations]\n"
            "name,type,latitude,longitude,map_x,map_y,description\n"
            "North Gate,gate,28.61,77.20,0.1,0.9,Main entrance\n"
            "Admin Block,building,28.62,77.21,0.5,0.5,Administrative hub\n"
            "[edges]\n"
            "source,destination,distance,path_name,is_blocked\n"
            "North Gate,Admin Block,200,Central Avenue,false\n"
        ).encode("utf-8")

    def test_valid_csv_parses_successfully(self):
        payload, errors, warnings = parse_and_validate_map_data(self._valid_csv(), "campus.csv")
        self.assertIsNotNone(payload)
        self.assertEqual(errors, [])
        self.assertEqual(len(payload["locations"]), 2)
        self.assertEqual(len(payload["edges"]), 1)
        self.assertAlmostEqual(payload["edges"][0]["distance"], 200.0)

    def test_csv_negative_distance_rejected(self):
        csv = (
            "[locations]\nname,type,map_x,map_y\nA,building,0.1,0.1\nB,building,0.5,0.5\n"
            "[edges]\nsource,destination,distance\nA,B,-100\n"
        ).encode("utf-8")
        payload, errors, _ = parse_and_validate_map_data(csv, "test.csv")
        self.assertIsNone(payload)


class TestMapParserXLSX(TestCase):
    """Unit tests for XLSX campus map template generation."""

    def test_template_xlsx_generates_non_empty_bytes(self):
        raw = generate_template_xlsx()
        self.assertIsInstance(raw, bytes)
        self.assertGreater(len(raw), 1000)

    def test_template_xlsx_is_parseable(self):
        raw = generate_template_xlsx()
        payload, errors, warnings = parse_and_validate_map_data(raw, "template.xlsx")
        self.assertIsNotNone(payload)
        self.assertEqual(errors, [])
        self.assertGreater(len(payload["locations"]), 0)
        self.assertGreater(len(payload["edges"]), 0)


class TestTemplateGeneration(TestCase):
    """Unit tests for downloadable template generation."""

    def test_json_template_is_valid_json(self):
        raw = generate_template_json()
        parsed = json.loads(raw)
        self.assertIn("locations", parsed)
        self.assertIn("edges", parsed)

    def test_json_template_passes_validation(self):
        raw = generate_template_json().encode("utf-8")
        payload, errors, _ = parse_and_validate_map_data(raw, "template.json")
        self.assertIsNotNone(payload)
        self.assertEqual(errors, [])

    def test_csv_template_passes_validation(self):
        raw = generate_template_csv().encode("utf-8")
        payload, errors, _ = parse_and_validate_map_data(raw, "template.csv")
        self.assertIsNotNone(payload)
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# Multi-Map API Integration Tests
# ---------------------------------------------------------------------------


class TestMultiMapAPI(TestCase):
    """Integration tests for the multi-map management API endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("testadmin", "admin@test.com", "testpass123")

    def setUp(self):
        self.client = Client()
        self.client.login(username="testadmin", password="testpass123")

    def _valid_json_bytes(self, map_name="Upload Test Campus"):
        data = {
            "map_name": map_name,
            "locations": [
                {"name": "Gate X", "type": "gate", "map_x": 0.1, "map_y": 0.2},
                {"name": "Lab Y", "type": "building", "map_x": 0.6, "map_y": 0.4},
            ],
            "edges": [
                {"source": "Gate X", "destination": "Lab Y", "distance": 150.0},
            ],
        }
        return json.dumps(data).encode("utf-8")

    def test_api_maps_list(self):
        res = self.client.get("/api/maps/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("maps", data)
        self.assertTrue(data["success"])

    def test_upload_preview_valid_file(self):
        file_obj = io.BytesIO(self._valid_json_bytes())
        file_obj.name = "test.json"
        res = self.client.post(
            "/api/maps/upload-preview/",
            {"file": file_obj},
            format="multipart",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["stats"]["total_locations"], 2)
        self.assertEqual(data["stats"]["total_pathways"], 1)

    def test_upload_preview_invalid_file(self):
        invalid_data = json.dumps({
            "map_name": "Bad Map",
            "locations": [{"name": "A", "type": "building", "map_x": 0.5, "map_y": 0.5}],
            "edges": [{"source": "A", "destination": "DoesNotExist", "distance": 100}],
        }).encode("utf-8")
        file_obj = io.BytesIO(invalid_data)
        file_obj.name = "bad.json"
        res = self.client.post("/api/maps/upload-preview/", {"file": file_obj})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["valid"])
        self.assertGreater(len(data["errors"]), 0)

    def test_upload_confirm_creates_map_and_data(self):
        initial_map_count = CampusMap.objects.count()
        file_obj = io.BytesIO(self._valid_json_bytes("Integration Test Map"))
        file_obj.name = "campus.json"
        res = self.client.post(
            "/api/maps/upload-confirm/",
            {"file": file_obj},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["stats"]["locations_created"], 2)
        self.assertEqual(data["stats"]["pathways_created"], 1)

        # Verify DB state
        self.assertEqual(CampusMap.objects.count(), initial_map_count + 1)
        new_map = CampusMap.objects.get(name="Integration Test Map")
        self.assertTrue(new_map.is_active)
        self.assertEqual(new_map.locations.count(), 2)
        self.assertEqual(new_map.edges.count(), 2)  # bidirectional

    def test_upload_confirm_conflict_without_replace(self):
        # Create map first
        CampusMap.objects.create(name="Existing Campus", description="pre-existing")
        file_obj = io.BytesIO(self._valid_json_bytes("Existing Campus"))
        file_obj.name = "campus.json"
        res = self.client.post("/api/maps/upload-confirm/", {"file": file_obj})
        data = res.json()
        self.assertFalse(data.get("success", True))
        self.assertTrue(data.get("conflict"))

    def test_upload_confirm_replace_existing(self):
        existing = CampusMap.objects.create(name="Replace Me", description="old data")
        file_obj = io.BytesIO(self._valid_json_bytes("Replace Me"))
        file_obj.name = "campus.json"
        res = self.client.post(
            "/api/maps/upload-confirm/",
            {"file": file_obj, "replace_existing": "true"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["success"])
        # Old map gone, new one created
        self.assertFalse(CampusMap.objects.filter(pk=existing.pk).exists())
        new_map = CampusMap.objects.get(name="Replace Me")
        self.assertEqual(new_map.locations.count(), 2)

    def test_set_active_map(self):
        map1 = CampusMap.objects.create(name="Map Alpha", is_active=True)
        map2 = CampusMap.objects.create(name="Map Beta", is_active=False)
        res = self.client.post(f"/api/maps/{map2.id}/set-active/")
        self.assertEqual(res.status_code, 200)
        map1.refresh_from_db()
        map2.refresh_from_db()
        self.assertFalse(map1.is_active)
        self.assertTrue(map2.is_active)

    def test_delete_map_requires_multiple_maps(self):
        # Clear all maps and create exactly one
        CampusMap.objects.all().delete()
        only_map = CampusMap.objects.create(name="Only Map")
        res = self.client.post(f"/api/maps/{only_map.id}/delete/")
        self.assertEqual(res.status_code, 400)  # Cannot delete last map

    def test_delete_map_success(self):
        m1 = CampusMap.objects.create(name="Map to Keep", is_active=True)
        m2 = CampusMap.objects.create(name="Map to Delete", is_active=False)
        res = self.client.post(f"/api/maps/{m2.id}/delete/")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(CampusMap.objects.filter(pk=m2.pk).exists())

    def test_template_download_json(self):
        res = self.client.get("/api/maps/template/?format=json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/json", res["Content-Type"])
        parsed = json.loads(res.content)
        self.assertIn("locations", parsed)

    def test_template_download_csv(self):
        res = self.client.get("/api/maps/template/?format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res["Content-Type"])

    def test_template_download_xlsx(self):
        res = self.client.get("/api/maps/template/?format=xlsx")
        self.assertEqual(res.status_code, 200)
        self.assertIn("spreadsheet", res["Content-Type"])

    def test_non_admin_cannot_upload(self):
        regular_user = User.objects.create_user("regularuser", password="pass123")
        self.client.login(username="regularuser", password="pass123")
        file_obj = io.BytesIO(self._valid_json_bytes())
        file_obj.name = "test.json"
        res = self.client.post("/api/maps/upload-preview/", {"file": file_obj})
        self.assertEqual(res.status_code, 403)

    def test_map_detail_endpoint(self):
        m = CampusMap.objects.create(name="Detail Test Map", is_active=True)
        res = self.client.get(f"/api/maps/{m.id}/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["map"]["name"], "Detail Test Map")
        self.assertIn("locations", data)
        self.assertIn("edges", data)
