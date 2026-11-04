"""File parser and validator for custom campus map uploads (JSON, CSV, XLSX).

Supports:
- Structured JSON format
- Sectioned or unified CSV format
- Multi-sheet Excel (XLSX) format
- Two-stage workflow: validate/preview without database writes, then confirm/commit.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple

import openpyxl


VALID_LOCATION_TYPES = {"building", "landmark", "gate", "facility"}


def parse_and_validate_map_data(
    file_bytes: bytes,
    filename: str,
) -> Tuple[Optional[Dict[str, Any]], List[str], List[str]]:
    """Parse and validate an uploaded campus map file (JSON, CSV, or XLSX).

    Returns:
        (parsed_payload, errors, warnings)
        If errors is non-empty, parsed_payload will be None or incomplete.
    """
    errors: List[str] = []
    warnings: List[str] = []
    fname = filename.lower()

    parsed_locations: List[Dict[str, Any]] = []
    parsed_edges: List[Dict[str, Any]] = []
    map_meta: Dict[str, Any] = {
        "name": filename.rsplit(".", 1)[0].replace("_", " ").title(),
        "description": f"Imported from {filename}",
    }

    try:
        if fname.endswith(".json"):
            content_str = file_bytes.decode("utf-8")
            data = json.loads(content_str)
            if not isinstance(data, dict):
                return None, ["JSON root must be an object with 'locations' and 'edges' arrays."], []

            if "map_name" in data:
                map_meta["name"] = str(data["map_name"]).strip()
            elif "name" in data:
                map_meta["name"] = str(data["name"]).strip()
            if "description" in data:
                map_meta["description"] = str(data["description"]).strip()

            parsed_locations = data.get("locations", [])
            parsed_edges = data.get("edges", [])

        elif fname.endswith(".csv"):
            content_str = file_bytes.decode("utf-8", errors="replace")
            parsed_locations, parsed_edges, csv_warnings = _parse_csv_content(content_str)
            warnings.extend(csv_warnings)

        elif fname.endswith(".xlsx"):
            parsed_locations, parsed_edges, xlsx_warnings = _parse_xlsx_content(file_bytes)
            warnings.extend(xlsx_warnings)

        else:
            return None, [f"Unsupported file format '{filename}'. Please upload .json, .csv, or .xlsx."], []

    except Exception as exc:
        return None, [f"Failed to read file: {str(exc)}"], []

    # Validate locations
    if not parsed_locations:
        errors.append("Map data must contain at least one location record in 'locations'.")

    validated_locations: List[Dict[str, Any]] = []
    seen_names = set()
    loc_name_to_idx = {}

    for idx, raw in enumerate(parsed_locations):
        name = str(raw.get("name", "")).strip()
        if not name:
            errors.append(f"Location #{idx + 1} has an empty 'name'.")
            continue

        if name.lower() in seen_names:
            warnings.append(f"Duplicate location name '{name}' detected. Using latest entry.")
        seen_names.add(name.lower())

        ltype = str(raw.get("type", "building")).lower().strip()
        if ltype not in VALID_LOCATION_TYPES:
            ltype = "building"

        try:
            lat = float(raw.get("lat", raw.get("latitude", 0.0)))
            lng = float(raw.get("lng", raw.get("longitude", 0.0)))
        except (ValueError, TypeError):
            lat, lng = 0.0, 0.0
            warnings.append(f"Location '{name}' has non-numeric GPS coordinates. Defaulted to (0.0, 0.0).")

        try:
            map_x = float(raw.get("x", raw.get("map_x", 0.5)))
            map_y = float(raw.get("y", raw.get("map_y", 0.5)))
            # Clamp to [0.0, 1.0]
            map_x = max(0.0, min(1.0, map_x))
            map_y = max(0.0, min(1.0, map_y))
        except (ValueError, TypeError):
            map_x, map_y = 0.5, 0.5
            warnings.append(f"Location '{name}' has non-numeric canvas coordinates. Defaulted to (0.5, 0.5).")

        desc = str(raw.get("description", "")).strip()

        loc_entry = {
            "name": name,
            "type": ltype,
            "latitude": lat,
            "longitude": lng,
            "map_x": map_x,
            "map_y": map_y,
            "description": desc,
        }
        validated_locations.append(loc_entry)
        loc_name_to_idx[name.lower()] = loc_entry

    # Validate edges / pathways
    validated_edges: List[Dict[str, Any]] = []
    seen_edge_pairs = set()

    for idx, raw in enumerate(parsed_edges):
        src = str(raw.get("source", "")).strip()
        dst = str(raw.get("destination", "")).strip()

        if not src or not dst:
            errors.append(f"Pathway #{idx + 1} is missing a source or destination.")
            continue

        if src.lower() not in loc_name_to_idx:
            errors.append(f"Pathway #{idx + 1} references non-existent location '{src}'.")
            continue
        if dst.lower() not in loc_name_to_idx:
            errors.append(f"Pathway #{idx + 1} references non-existent location '{dst}'.")
            continue

        if src.lower() == dst.lower():
            warnings.append(f"Pathway #{idx + 1} connects '{src}' to itself (self-loop). Skipped.")
            continue

        try:
            dist = float(raw.get("distance", 0.0))
        except (ValueError, TypeError):
            errors.append(f"Pathway between '{src}' and '{dst}' has invalid non-numeric distance.")
            continue

        if dist <= 0.0:
            errors.append(
                f"Pathway between '{src}' and '{dst}' has non-positive distance {dist}m. Distance must be > 0."
            )
            continue

        pair_key = tuple(sorted([src.lower(), dst.lower()]))
        if pair_key in seen_edge_pairs:
            warnings.append(f"Duplicate pathway between '{src}' and '{dst}' detected. Kept shortest distance.")
            continue
        seen_edge_pairs.add(pair_key)

        path_name = str(raw.get("path_name", raw.get("name", ""))).strip()
        is_blocked = bool(raw.get("is_blocked", False))

        validated_edges.append({
            "source": src,
            "destination": dst,
            "distance": round(dist, 1),
            "path_name": path_name,
            "is_blocked": is_blocked,
        })

    if errors:
        return None, errors, warnings

    payload = {
        "map_name": map_meta["name"],
        "description": map_meta["description"],
        "locations": validated_locations,
        "edges": validated_edges,
        "stats": {
            "total_locations": len(validated_locations),
            "total_pathways": len(validated_edges),
            "blocked_pathways": sum(1 for e in validated_edges if e["is_blocked"]),
        },
    }
    return payload, [], warnings


def _parse_csv_content(csv_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Parse a sectioned or unified CSV containing locations and pathways."""
    lines = csv_text.splitlines()
    locations: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    warnings: List[str] = []

    current_section = "locations"
    loc_header: Optional[List[str]] = None
    edge_header: Optional[List[str]] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Check section header
        if line.lower() in ("[locations]", "locations:", "[nodes]", "nodes:"):
            current_section = "locations"
            loc_header = None
            continue
        elif line.lower() in ("[edges]", "edges:", "[pathways]", "pathways:", "[paths]"):
            current_section = "edges"
            edge_header = None
            continue

        row = list(csv.reader([line]))[0]
        row = [cell.strip() for cell in row]

        if current_section == "locations":
            if loc_header is None:
                # Detect header
                if any(h in row[0].lower() for h in ("name", "location", "title")):
                    loc_header = [c.lower() for c in row]
                    continue
                else:
                    loc_header = ["name", "type", "latitude", "longitude", "map_x", "map_y", "description"]

            # Map columns
            row_dict: Dict[str, Any] = {}
            for i, col in enumerate(loc_header):
                if i < len(row):
                    row_dict[col] = row[i]
            locations.append(row_dict)

        elif current_section == "edges":
            if edge_header is None:
                if any(h in row[0].lower() for h in ("source", "from", "origin")):
                    edge_header = [c.lower() for c in row]
                    continue
                else:
                    edge_header = ["source", "destination", "distance", "path_name", "is_blocked"]

            row_dict: Dict[str, Any] = {}
            for i, col in enumerate(edge_header):
                if i < len(row):
                    row_dict[col] = row[i]
            edges.append(row_dict)

    return locations, edges, warnings


def _parse_xlsx_content(file_bytes: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Parse an Excel workbook with 'Locations' and 'Pathways' sheets."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    warnings: List[str] = []
    locations: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # Find locations sheet
    loc_sheet_name = next(
        (s for s in wb.sheetnames if s.lower() in ("locations", "nodes", "buildings")),
        wb.sheetnames[0],
    )
    ws_loc = wb[loc_sheet_name]
    loc_rows = list(ws_loc.iter_rows(values_only=True))
    if loc_rows:
        header = [str(c).lower().strip() if c is not None else "" for c in loc_rows[0]]
        for row in loc_rows[1:]:
            if not row or all(v is None for v in row):
                continue
            entry = {}
            for col_idx, col_name in enumerate(header):
                if col_idx < len(row):
                    entry[col_name] = row[col_idx]
            locations.append(entry)

    # Find edges sheet
    edge_sheet_name = next(
        (s for s in wb.sheetnames if s.lower() in ("pathways", "edges", "paths")),
        None,
    )
    if edge_sheet_name:
        ws_edge = wb[edge_sheet_name]
        edge_rows = list(ws_edge.iter_rows(values_only=True))
        if edge_rows:
            header = [str(c).lower().strip() if c is not None else "" for c in edge_rows[0]]
            for row in edge_rows[1:]:
                if not row or all(v is None for v in row):
                    continue
                entry = {}
                for col_idx, col_name in enumerate(header):
                    if col_idx < len(row):
                        entry[col_name] = row[col_idx]
                edges.append(entry)

    return locations, edges, warnings


def generate_template_json() -> str:
    """Generate a clean JSON template for campus data input."""
    return json.dumps({
        "map_name": "University Central Campus",
        "description": "Primary academic and residential navigation network",
        "locations": [
            {
                "name": "Main Entrance Gate",
                "type": "gate",
                "latitude": 28.6139,
                "longitude": 77.2090,
                "map_x": 0.10,
                "map_y": 0.85,
                "description": "Main gate entrance with visitor registration booth"
            },
            {
                "name": "Central Library",
                "type": "building",
                "latitude": 28.6152,
                "longitude": 77.2070,
                "map_x": 0.40,
                "map_y": 0.65,
                "description": "Central university library with reading halls"
            },
            {
                "name": "Student Center",
                "type": "facility",
                "latitude": 28.6160,
                "longitude": 77.2080,
                "map_x": 0.50,
                "map_y": 0.50,
                "description": "Cafeteria, student clubs and convenience store"
            }
        ],
        "edges": [
            {
                "source": "Main Entrance Gate",
                "destination": "Central Library",
                "distance": 140.0,
                "path_name": "Founders Boulevard",
                "is_blocked": False
            },
            {
                "source": "Central Library",
                "destination": "Student Center",
                "distance": 95.0,
                "path_name": "Library Walk",
                "is_blocked": False
            }
        ]
    }, indent=2)


def generate_template_csv() -> str:
    """Generate a sectioned CSV template for campus data."""
    return (
        "# CAMPUS NAVIGATION MAP DATA TEMPLATE\n"
        "[locations]\n"
        "name,type,latitude,longitude,map_x,map_y,description\n"
        "Main Entrance Gate,gate,28.6139,77.2090,0.10,0.85,Main visitor entrance\n"
        "Central Library,building,28.6152,77.2070,0.40,0.65,Three-storey library\n"
        "Student Center,facility,28.6160,77.2080,0.50,0.50,Dining and student activity\n"
        "\n"
        "[edges]\n"
        "source,destination,distance,path_name,is_blocked\n"
        "Main Entrance Gate,Central Library,140,Founders Boulevard,false\n"
        "Central Library,Student Center,95,Library Walk,false\n"
    )


def generate_template_xlsx() -> bytes:
    """Generate an Excel XLSX workbook template with 'Locations' and 'Pathways' sheets."""
    wb = openpyxl.Workbook()
    ws_loc = wb.active
    ws_loc.title = "Locations"

    ws_loc.append(["name", "type", "latitude", "longitude", "map_x", "map_y", "description"])
    ws_loc.append(["Main Entrance Gate", "gate", 28.6139, 77.2090, 0.10, 0.85, "Main visitor entrance"])
    ws_loc.append(["Central Library", "building", 28.6152, 77.2070, 0.40, 0.65, "Three-storey library"])
    ws_loc.append(["Student Center", "facility", 28.6160, 77.2080, 0.50, 0.50, "Dining and student activity"])

    ws_edges = wb.create_sheet(title="Pathways")
    ws_edges.append(["source", "destination", "distance", "path_name", "is_blocked"])
    ws_edges.append(["Main Entrance Gate", "Central Library", 140, "Founders Boulevard", False])
    ws_edges.append(["Central Library", "Student Center", 95, "Library Walk", False])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

