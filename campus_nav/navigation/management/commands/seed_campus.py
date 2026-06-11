"""
Django management command to seed the campus navigation database with sample data.

Creates 15+ realistic campus locations and 25+ bidirectional edges with
realistic distances. Makes 3-4 edges blockable for demo purposes.
"""
from django.core.management.base import BaseCommand
from navigation.models import Location, Edge


class Command(BaseCommand):
    """Seed the campus database with realistic locations and paths."""

    help = 'Populate the database with campus locations and paths'

    def handle(self, *args, **options):
        self.stdout.write('Seeding campus navigation data...')

        # Clear existing data
        Edge.objects.all().delete()
        Location.objects.all().delete()

        # Define campus locations (name, type, lat, lng, description)
        # Using a local coordinate system (arbitrary origin) for simplicity
        locations_data = [
            # Gates
            ('Main Gate', 'gate', 0.0, 0.0, 'Primary campus entrance'),
            ('North Gate', 'gate', 0.0, 500.0, 'Northern entrance near hostels'),
            ('East Gate', 'gate', 500.0, 250.0, 'Eastern entrance near sports complex'),
            ('West Gate', 'gate', -500.0, 250.0, 'Western entrance near staff quarters'),

            # Academic Buildings
            ('Admin Block', 'building', 100.0, 100.0, 'Central administration offices'),
            ('Library', 'building', 200.0, 150.0, 'Central library with 500k+ volumes'),
            ('CS Department', 'building', 300.0, 100.0, 'Computer Science & Engineering department'),
            ('EE Department', 'building', 300.0, 200.0, 'Electrical Engineering department'),
            ('Mech Department', 'building', 250.0, 300.0, 'Mechanical Engineering department'),
            ('Science Block', 'building', 150.0, 250.0, 'Physics, Chemistry, Mathematics departments'),
            ('Lecture Hall Complex', 'building', 50.0, 200.0, 'Main lecture theaters and classrooms'),

            # Student Facilities
            ('Student Center', 'building', -50.0, 150.0, 'Student union, clubs, cafeteria'),
            ('Canteen', 'building', 0.0, 200.0, 'Main campus canteen and food court'),
            ('Hostel A', 'building', -100.0, 400.0, 'Undergraduate boys hostel'),
            ('Hostel B', 'building', -100.0, 500.0, 'Undergraduate girls hostel'),
            ('Hostel C', 'building', 100.0, 450.0, 'Postgraduate hostel'),

            # Sports & Recreation
            ('Sports Ground', 'landmark', 400.0, 350.0, 'Main sports field and track'),
            ('Indoor Stadium', 'building', 450.0, 300.0, 'Badminton, basketball, table tennis'),
            ('Swimming Pool', 'landmark', 500.0, 200.0, 'Olympic-size swimming pool'),

            # Other
            ('Auditorium', 'building', 200.0, 50.0, 'Main auditorium for events'),
            ('Health Center', 'building', -150.0, 100.0, 'Campus medical facility'),
            ('Research Park', 'landmark', 400.0, 0.0, 'Innovation and research center'),
        ]

        # Create locations
        locations = {}
        for name, loc_type, lat, lng, desc in locations_data:
            loc = Location.objects.create(
                name=name,
                type=loc_type,
                latitude=lat,
                longitude=lng,
                description=desc
            )
            locations[name] = loc
            self.stdout.write(f'  Created location: {name}')

        # Define edges (source, destination, distance_meters, path_name, is_blockable)
        # Using realistic walking distances
        edges_data = [
            # Main Gate connections
            ('Main Gate', 'Admin Block', 140, 'Main Avenue', False),
            ('Main Gate', 'Student Center', 160, 'Welcome Path', False),
            ('Main Gate', 'Lecture Hall Complex', 220, 'Academic Walk', False),
            ('Main Gate', 'Auditorium', 220, 'Event Path', False),

            # Admin Block connections
            ('Admin Block', 'Library', 110, 'Library Lane', False),
            ('Admin Block', 'Lecture Hall Complex', 150, 'Academic Corridor', False),
            ('Admin Block', 'Science Block', 180, 'Science Walk', False),
            ('Admin Block', 'Student Center', 150, 'Central Plaza', True),  # Blockable

            # Library connections
            ('Library', 'CS Department', 140, 'Tech Bridge', False),
            ('Library', 'Science Block', 120, 'Knowledge Path', False),
            ('Library', 'Canteen', 130, 'Food Court Walk', True),  # Blockable

            # Department connections
            ('CS Department', 'EE Department', 100, 'Engineering Corridor', False),
            ('EE Department', 'Mech Department', 140, 'Workshop Way', False),
            ('Mech Department', 'Science Block', 110, 'Lab Link', False),
            ('Science Block', 'Lecture Hall Complex', 160, 'Classroom Connect', False),

            # Student Center area
            ('Student Center', 'Canteen', 80, 'Food Street', False),
            ('Student Center', 'Health Center', 130, 'Wellness Way', False),
            ('Canteen', 'Hostel A', 250, 'Hostel Highway', False),
            ('Canteen', 'Hostel B', 350, 'Hostel Highway', False),

            # Hostel connections
            ('Hostel A', 'Hostel B', 120, 'Hostel Link', False),
            ('Hostel A', 'Hostel C', 180, 'PG Connect', False),
            ('Hostel B', 'North Gate', 100, 'Gate Access', True),  # Blockable

            # Sports complex
            ('CS Department', 'Sports Ground', 200, 'Sports Access', False),
            ('Sports Ground', 'Indoor Stadium', 80, 'Stadium Path', False),
            ('Indoor Stadium', 'Swimming Pool', 120, 'Aqua Walk', False),
            ('East Gate', 'Sports Ground', 150, 'Sports Entry', False),
            ('East Gate', 'Swimming Pool', 100, 'Pool Access', False),

            # Research Park
            ('CS Department', 'Research Park', 180, 'Innovation Trail', False),
            ('Research Park', 'EE Department', 160, 'Research Link', False),

            # West side
            ('West Gate', 'Health Center', 200, 'Medical Access', False),
            ('West Gate', 'Student Center', 300, 'West Campus Way', False),
            ('Admin Block', 'Auditorium', 130, 'Event Corridor', True),  # Blockable

            # Cross-campus shortcuts
            ('Library', 'Canteen', 150, 'Diagonal Shortcut', False),
            ('Science Block', 'Hostel C', 220, 'Hostel Shortcut', False),
        ]

        # Create edges (bidirectional)
        edge_count = 0
        for src_name, dst_name, distance, path_name, is_blockable in edges_data:
            src = locations[src_name]
            dst = locations[dst_name]

            # Create forward edge
            edge1 = Edge.objects.create(
                source=src,
                destination=dst,
                distance=distance,
                path_name=path_name,
                is_blocked=False
            )
            edge_count += 1

            # Create reverse edge
            edge2 = Edge.objects.create(
                source=dst,
                destination=src,
                distance=distance,
                path_name=path_name,
                is_blocked=False
            )
            edge_count += 1

            self.stdout.write(f'  Created edge: {src_name} ↔ {dst_name} ({distance}m)')

        # Mark a few edges as blockable (demo purposes)
        # We'll just note which ones are blockable in the path_name for now
        # The actual blocking is done via the API

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully seeded {len(locations)} locations and {edge_count} edges!'
            )
        )
        self.stdout.write('\nBlockable edges (for demo):')
        self.stdout.write('  - Admin Block ↔ Student Center (Central Plaza)')
        self.stdout.write('  - Library ↔ Canteen (Food Court Walk)')
        self.stdout.write('  - Hostel B ↔ North Gate (Gate Access)')
        self.stdout.write('  - Admin Block ↔ Auditorium (Event Corridor)')