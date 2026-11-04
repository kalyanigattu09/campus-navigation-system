# Deployment Guide — Render + PostgreSQL

This guide walks you through deploying the Campus Navigation System to Render using a native Python Web Service and a Render PostgreSQL database.

> **Important**: Deploy from the `campus-navigation-redesign` branch only. Never push to `main`.

---

## Prerequisites

- A [Render](https://render.com) account (free tier works)
- Your repository pushed to GitHub on branch `campus-navigation-redesign`

---

## Step 1: Create a PostgreSQL Database on Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **PostgreSQL**
3. Set the following:
   - **Name**: `campus-nav-db`
   - **Plan**: Free
   - **Region**: Choose closest to your users
4. Click **Create Database**
5. Wait for the database to become available (~1 minute)
6. Copy the **Internal Database URL** — you'll need it in Step 2

---

## Step 2: Create a Web Service on Render

1. Click **New +** → **Web Service**
2. Connect your GitHub repository
3. Select the repository and set:
   - **Branch**: `campus-navigation-redesign`
   - **Root Directory**: *(leave blank)*
   - **Environment**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn campus_nav.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
4. Under **Environment Variables**, add:
   | Key | Value |
   |-----|-------|
   | `DJANGO_SECRET_KEY` | *(click "Generate")* |
   | `DJANGO_DEBUG` | `False` |
   | `DJANGO_ALLOWED_HOSTS` | `.onrender.com` |
   | `DATABASE_URL` | *(paste Internal Database URL from Step 1)* |
5. Click **Create Web Service**

---

## Step 3: Create the Admin User

After the first successful deploy, open the Render **Shell** tab and run:

```bash
python manage.py createsuperuser
```

Enter a username, email, and password when prompted.

---

## Step 4: Verify the Deployment

1. Visit your Render app URL: `https://campus-navigation.onrender.com` (or your chosen name)
2. Navigate to `/admin-login/` and sign in with the superuser credentials
3. Upload your campus map data via the Admin Dashboard → Map Management

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | ✅ Yes | 50+ character random secret key |
| `DJANGO_DEBUG` | ✅ Yes | Set to `False` in production |
| `DJANGO_ALLOWED_HOSTS` | ✅ Yes | Comma-separated allowed host domains |
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string from Render |

---

## Local Development

For local development, copy `.env.example` to `.env` and set your values:

```bash
cp .env.example .env
```

The app uses SQLite locally (no extra setup) and PostgreSQL automatically on Render.

Run locally:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `DisallowedHost` error | Add your domain to `DJANGO_ALLOWED_HOSTS` env var |
| Static files not loading | Ensure `whitenoise` is in `INSTALLED_APPS` and `MIDDLEWARE` |
| Database connection error | Verify `DATABASE_URL` is set correctly and database is running |
| `ModuleNotFoundError` | Check `requirements.txt` has all dependencies |
