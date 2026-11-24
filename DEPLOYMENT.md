# Deployment Guide — Render + PostgreSQL

This guide provides the complete, tested procedure for deploying the **Campus Navigation System** to [Render](https://render.com) using native Python and PostgreSQL.

---

## Prerequisites
- A free account on [Render](https://dashboard.render.com).
- Repository pushed to GitHub on branch `campus-navigation-redesign`.

---

## Method 1: Automated Blueprint Deploy (Recommended — 1-Click)

The repository contains `render.yaml`, which automatically sets up the Python web service, builds the assets, provisions the PostgreSQL database, and links them together.

1. Go to the [Render Dashboard](https://dashboard.render.com).
2. Click **New +** (top right) → **Blueprint**.
3. Select your repository: `kalyanigattu09/campus-navigation-system`.
4. Set **Branch** to: `campus-navigation-redesign`.
5. Render will show the two linked resources:
   - **Database**: `campus-nav-db` (PostgreSQL Free)
   - **Web Service**: `campus-navigation` (Python 3 Free)
6. Click **Apply**.
7. Wait ~2–3 minutes while Render runs `build.sh` (installs packages, runs migrations, and collects static files).

---

## Method 2: Manual Deploy

If you prefer setting it up step-by-step:

### 1. Create the Database
1. Click **New +** → **PostgreSQL**.
2. **Name**: `campus-nav-db`
3. **Plan**: Free
4. Click **Create Database** and copy the **Internal Database URL**.

### 2. Create the Web Service
1. Click **New +** → **Web Service**.
2. Connect your repo and set branch to `campus-navigation-redesign`.
3. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn campus_nav.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Plan**: Free
4. **Environment Variables**:
   - `DATABASE_URL`: *(paste Internal Database URL)*
   - `DJANGO_SECRET_KEY`: *(click Generate)*
   - `DJANGO_DEBUG`: `False`
   - `DJANGO_ALLOWED_HOSTS`: `.onrender.com`
   - `CSRF_TRUSTED_ORIGINS`: `https://*.onrender.com`
   - `PYTHON_VERSION`: `3.11.0`
5. Click **Create Web Service**.

---

## Creating the Admin Superuser

Once the deployment shows **Live**:
1. Click your web service on Render → **Shell** (left sidebar).
2. Run:
   ```bash
   python manage.py createsuperuser
   ```
3. Enter your username, email, and password.

Log in at `https://<your-app-name>.onrender.com/admin-login/` to manage maps, pathways, and locations.

---

## ⚡ PRO TIP: Prevent Cold Starts (Keep App Awake 24/7)

Render's free tier spins down web services after 15 minutes of inactivity, causing a 30–50 second delay on the next visit.

**To keep your app instantly fast at all times for free:**
1. Go to **[cron-job.org](https://cron-job.org)** or **[uptimerobot.com](https://uptimerobot.com)** (both 100% free).
2. Create an account and add a new monitor/job:
   - **URL**: `https://<your-app-name>.onrender.com/api/campus-graph/`
   - **Schedule / Interval**: Every **10 minutes**.
3. That's it! The monitor sends a lightweight ping every 10 minutes, preventing Render from ever sleeping. Your app will load immediately for anyone visiting at any time.
