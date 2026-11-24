#!/usr/bin/env bash
# Render build script — runs on every deploy
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Seed sample campus data if DB is empty
python manage.py shell -c "
from navigation.models import CampusMap, Location
if CampusMap.objects.count() == 0:
    try:
        from django.core.management import call_command
        call_command('seed_campus', '--sample')
        print('Campus data seeded.')
    except Exception as e:
        print('Seed skipped:', e)
else:
    print('Campus data already present:', Location.objects.count(), 'locations')
"

# Create/reset admin superuser
python manage.py shell -c "
from django.contrib.auth.models import User
import os
uname = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
passwd = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123')
email  = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@campus.local')
u, created = User.objects.get_or_create(username=uname)
u.set_password(passwd)
u.is_staff = True
u.is_superuser = True
u.is_active = True
u.email = email
u.save()
print(f'Admin user [{uname}] {\"created\" if created else \"updated\"} — OK')
"

# Create demo user
python manage.py shell -c "
from django.contrib.auth.models import User
d, dc = User.objects.get_or_create(username='demo')
d.set_password('demo1234')
d.is_active = True
d.is_staff = False
d.is_superuser = False
d.save()
print('Demo user', 'created' if dc else 'updated', '— OK')
"
