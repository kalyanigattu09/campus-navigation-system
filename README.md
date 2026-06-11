# Campus Navigation System

A full-stack campus navigation web application that finds the shortest walking
route between campus locations using Dijkstra's algorithm with a min-heap
priority queue. Built with Django, vanilla HTML/CSS/JavaScript, SQLite, and a
responsive animated canvas map.

## Features

- Shortest-path routing across 18 campus locations and 28 bidirectional paths.
- Live road block manager: mark roads open or blocked and re-route in real time.
- Animated canvas map with glowing nodes, blocked roads, route highlighting, and
  a moving route marker.
- Turn-by-turn walking instructions with distance and direction labels.
- Alternative route option computed by re-running Dijkstra while blocking one
  primary-route edge at a time.
- Visualize Dijkstra mode with visited-node highlighting and priority queue
  replay controls.
- Searchable source and destination selectors plus click-to-select map nodes.
- Stats ticker for live location, path, and blocked-road counts.

## Project Structure

```text
campus-navigation-project/
|-- manage.py
|-- requirements.txt
|-- README.md
|-- db.sqlite3
|-- campus_nav/
|   |-- __init__.py
|   |-- settings.py
|   |-- urls.py
|   `-- wsgi.py
`-- navigation/
    |-- __init__.py
    |-- models.py
    |-- views.py
    |-- urls.py
    |-- utils/
    |   |-- __init__.py
    |   |-- graph.py
    |   `-- instructions.py
    |-- management/
    |   |-- __init__.py
    |   `-- commands/
    |       |-- __init__.py
    |       `-- seed_campus.py
    `-- templates/
        `-- navigation/
            `-- index.html
```

## Setup & Run

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_campus
python manage.py runserver
```

Open `http://127.0.0.1:8000`.

The seed command creates 18 locations and 56 directed `Edge` rows, representing
28 bidirectional campus paths. Four bidirectional paths start blocked for demo
purposes.

By default, SQLite is stored outside the OneDrive project folder in a local
runtime directory to avoid cloud-sync file locking. Set `CAMPUS_NAV_DB_PATH` if
you want to choose a specific database file.

## API Reference

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/locations/` | All campus locations |
| GET | `/api/edges/` | All directed edges with blocked status |
| GET | `/api/campus-graph/` | Combined `{locations, edges, stats}` payload |
| POST | `/api/find-path/` | Shortest route for `{source_id, destination_id, blocked_ids, avoid_blocked, emergency}` |
| POST | `/api/toggle-block/` | Updates both directions for `{edge_id, is_blocked}` |
| POST | `/api/visualize/` | Dijkstra trace for `{source_id, destination_id, blocked_ids, avoid_blocked}` |

The frontend uses `fetch()` with `async/await`; API failures appear as error
toasts.

## Dijkstra Implementation

The core algorithm lives in `navigation/utils/graph.py`. It builds an adjacency
list from active `Edge` rows, skipping persisted blocked roads unless the
frontend asks to include them, and always skipping any edge ids passed in
`blocked_ids`.

```python
adjacency: Dict[int, List[Tuple[int, float, int]]] = {}
for edge in edges:
    if edge.id in blocked or (edge.is_blocked and not include_db_blocked):
        continue
    adjacency.setdefault(edge.source_id, []).append(
        (edge.destination_id, edge.distance, edge.id)
    )
    adjacency.setdefault(edge.destination_id, []).append(
        (edge.source_id, edge.distance, edge.id)
    )
```

Dijkstra uses Python's `heapq` as a binary min-heap:

```python
distances = {source_id: 0.0}
previous = {}
heap = [(0.0, source_id)]

while heap:
    d, u = heapq.heappop(heap)
    if u in seen:
        continue
    seen.add(u)
    if u == destination_id:
        break
    for v, w, _ in adjacency.get(u, []):
        nd = d + w
        if nd < distances.get(v, float("inf")):
            distances[v] = nd
            previous[v] = u
            heapq.heappush(heap, (nd, v))
```

Time complexity is `O((V + E) log V)`: each edge relaxation may push a candidate
distance into the heap, and each heap operation costs `log V`. The min-heap is
used because Dijkstra must always expand the currently cheapest known node.

If the destination cannot be reached, the algorithm raises `NoPathException`.
The API converts that into a 404 JSON response, and the UI displays it as a
toast.

Estimated travel time uses a walking speed of `1.2 m/s`, so:

```text
travel_time_seconds = total_distance_meters / 1.2
```

## Frontend Notes

- No npm or build step is required.
- The canvas is responsive and device-pixel-ratio aware.
- The map supports click-to-select, drag-to-pan, and wheel-to-zoom.
- Route animation uses a single `requestAnimationFrame` loop.
- Visualize mode replays Dijkstra with queue snapshots from the backend.

## Quality Bars

- No placeholders.
- Django views return `JsonResponse` objects with error handling.
- Dijkstra handles disconnected graphs gracefully.
- The UI works with vanilla JavaScript only.
- Core modules include docstrings and are PEP 8 friendly.
