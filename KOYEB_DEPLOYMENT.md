# Deployment Guide — Koyeb + Neon PostgreSQL

This guide walks you through deploying the **Campus Navigation System** using **Koyeb** (for the web application) and **Neon** (for free, permanent serverless PostgreSQL).

---

## Why Koyeb + Neon?
- **No 90-day expiry**: Neon's free tier never deletes your PostgreSQL database.
- **Fast response**: Low latency with global edge networking.
- **Free tier friendly**: Zero credit card required for either service.
- **Auto-deployment**: Automatically redeploys when you push to GitHub.

---

## Step 1: Create Free PostgreSQL Database on Neon

1. Go to [neon.tech](https://neon.tech) and sign up with your GitHub account.
2. Click **Create Project**:
   - **Name**: `campus-navigation-db`
   - **Database name**: `neondb` (default)
   - **Region**: Pick the region closest to you (e.g. `US East`, `Europe`, `Asia`)
3. Once created, you will see your **Connection Details**:
   - Make sure **Connection String** is selected.
   - Copy the string that looks like:
     ```text
     postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz-pooler.region.aws.neon.tech/neondb?sslmode=require
     ```
   *(Keep this string handy — you'll use it as `DATABASE_URL` in Step 2).*

---

## Step 2: Deploy the Web Service on Koyeb

1. Go to [koyeb.com](https://www.koyeb.com) and sign up / sign in with your GitHub account.
2. In the Koyeb dashboard, click **Create Service** or **Deploy**.
3. Choose **GitHub** as the deployment method.
4. Select your repository: `kalyanigattu09/campus-navigation-system`.
5. Configure the deployment settings:
   - **Branch**: `campus-navigation-redesign`
   - **Builder**: **Buildpack** (default)
   - **Build Command**: `bash build.sh`
   - **Run Command**: `gunicorn campus_nav.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` (or leave empty to let `Procfile` handle it)
6. Under **Environment Variables**, add the following 4 variables:

   | Name | Value | Description |
   |---|---|---|
   | `DATABASE_URL` | *(Paste Neon Connection String from Step 1)* | Links to your Neon PostgreSQL |
   | `DJANGO_SECRET_KEY` | *(Enter any random 50-character string)* | Django security key |
   | `DJANGO_DEBUG` | `False` | Disables debug mode in production |
   | `DJANGO_ALLOWED_HOSTS` | `.koyeb.app` | Allows your Koyeb domain |
   | `CSRF_TRUSTED_ORIGINS` | `https://*.koyeb.app` | Allows secure POST requests |

7. Choose the **Free Eco Instance** (Nano or Micro).
8. Click **Deploy**.

---

## Step 3: Create Superuser (Admin Account)

Once the app deployment shows **Healthy**:

1. In the Koyeb dashboard, open your service.
2. Click the **Console** / **Exec** tab (web terminal).
3. Run:
   ```bash
   python manage.py createsuperuser
   ```
4. Enter your chosen username, email, and password.

---

## Step 4: Access Your Public Application

Your application is now live at:
`https://<your-service-name>-<org-name>.koyeb.app`

- Open the root URL `/` to view the interactive campus navigation map.
- Open `/admin-login/` to log in with your superuser account and upload campus map data (CSV / JSON / XLSX).
