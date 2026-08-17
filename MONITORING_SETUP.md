# Monitoring Setup Guide

## Overview

This guide will help you set up professional monitoring for your Agent Observability System:
1. **Sentry** - Real-time error tracking and performance monitoring
2. **UptimeRobot** - 24/7 uptime monitoring and alerts

---

## Part 1: Sentry Error Monitoring

### Why Sentry?
- Automatic error capturing with full stack traces
- Performance monitoring for API endpoints
- Real-time alerts via email/Slack/Discord
- Error grouping and trend analysis
- Free tier: 5,000 errors/month

### Step 1: Create Sentry Account

1. **Go to Sentry:** https://sentry.io/signup/
2. **Sign up** with your GitHub account (easiest)
3. **Choose plan:** Select "Developer" (Free)

### Step 2: Create Project

1. After signup, click **"Create Project"**
2. **Select Platform:** Python
3. **Choose Framework:** FastAPI
4. **Project Name:** `agent-observability-system`
5. **Alert Frequency:** Default is fine
6. Click **"Create Project"**

### Step 3: Get Your DSN

After creating the project, Sentry will show you a DSN (Data Source Name):

```
https://abc123def456@o123456.ingest.sentry.io/7890123
```

**Copy this DSN!** You'll need it in the next step.

### Step 4: Add DSN to Your Environment

**Edit your `.env` file:**

```bash
# Add this line with YOUR actual DSN
SENTRY_DSN=https://abc123def456@o123456.ingest.sentry.io/7890123
```

**Example:**
```bash
DATABASE_URL=postgresql://postgres:DVkp4ZH97AsM1Dpi@db.xjdlvkhtfceyulhqpgmj.supabase.co:5432/postgres
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
SENTRY_DSN=https://abc123def456@o123456.ingest.sentry.io/7890123
```

### Step 5: Install Sentry SDK

```bash
# Activate your virtual environment first
.\venv\Scripts\activate

# Install Sentry SDK with FastAPI integration
pip install sentry-sdk[fastapi]
```

### Step 6: Restart Your API

```bash
# Stop your current API (Ctrl+C if running)

# Start it again
uvicorn api.main:app --reload --port 8001
```

You should see:
```
✅ Sentry error monitoring enabled
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### Step 7: Test Sentry Integration

**Test the error tracking:**

```bash
# This endpoint will trigger a test error
curl http://localhost:8001/sentry-debug
```

**Check Sentry Dashboard:**
1. Go to https://sentry.io
2. Open your project: `agent-observability-system`
3. Click "Issues" in the left sidebar
4. You should see a `ZeroDivisionError` captured!

**What you'll see:**
- Error message: "division by zero"
- Full stack trace
- Request details (URL, method, headers)
- Environment info (Python version, OS)
- Timestamp

### Step 8: Test with Real Error (Optional)

**Trigger an auth error:**

```bash
# Try to access protected endpoint without API key
curl -X POST http://localhost:8001/ingest_trace
```

This 401 error won't be sent to Sentry (by design - HTTP errors aren't exceptions).

**Trigger a real server error:**

Send invalid JSON to cause a parsing error:
```bash
curl -X POST http://localhost:8001/ingest_trace \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d "invalid json{"
```

Check Sentry - you should see this error captured!

---

## Part 2: UptimeRobot Monitoring

### Why UptimeRobot?
- 24/7 uptime monitoring (checks every 5 minutes)
- Email/SMS/Slack alerts when your API goes down
- Public status page option
- Response time tracking
- Free tier: 50 monitors

### Important Note
UptimeRobot needs a **public URL** to monitor. You have 3 options:

**Option A: Deploy First (Recommended)**
- Deploy to Railway, Render, or Heroku
- Get public URL
- Then set up UptimeRobot

**Option B: Use ngrok (Temporary Testing)**
- Create temporary public tunnel to localhost
- Good for testing monitoring setup
- URL changes each time you restart

**Option C: Skip for Now**
- Set up UptimeRobot later after deployment

### Option B: Quick Test with ngrok

If you want to test UptimeRobot now:

**1. Install ngrok:**
- Download from: https://ngrok.com/download
- Sign up for free account
- Extract and run ngrok

**2. Create tunnel to your local API:**
```bash
ngrok http 8001
```

**3. Copy the public URL:**
```
Forwarding: https://abc123.ngrok-free.app -> http://localhost:8001
```

**4. Test it works:**
```bash
curl https://abc123.ngrok-free.app/health
```

Now continue with UptimeRobot setup below using this URL.

### Step 1: Create UptimeRobot Account

1. **Go to:** https://uptimerobot.com/signUp
2. **Sign up** (Free plan)
3. **Verify email**

### Step 2: Add Monitor for API Health

1. Click **"+ Add New Monitor"**
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** `Agent Observability API - Health`
4. **URL:** 
   - If deployed: `https://your-domain.com/health`
   - If using ngrok: `https://abc123.ngrok-free.app/health`
5. **Monitoring Interval:** 5 minutes
6. Click **"Create Monitor"**

### Step 3: Add Monitor for API Stats

1. Click **"+ Add New Monitor"**
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** `Agent Observability API - Stats`
4. **URL:**
   - If deployed: `https://your-domain.com/stats`
   - If using ngrok: `https://abc123.ngrok-free.app/stats`
5. **Monitoring Interval:** 5 minutes
6. Click **"Create Monitor"**

### Step 4: Set Up Alerts

1. Go to **"My Settings"** (top right)
2. Click **"Alert Contacts"**
3. **Add your email:**
   - Email address
   - Verify email
4. **Configure when to alert:**
   - ✅ When monitor goes DOWN
   - ✅ When monitor comes back UP
   - Repeat alerts: Every 60 minutes (if still down)

### Step 5: Optional - Public Status Page

Create a public status page to share system status:

1. Go to **"Status Pages"** (left sidebar)
2. Click **"Add New Status Page"**
3. **Name:** Agent Observability System Status
4. **Select monitors** to display (both health and stats)
5. **Customize** look and feel
6. Click **"Create Status Page"**
7. **Copy the public URL** (e.g., `https://stats.uptimerobot.com/xyz123`)

You can share this URL with users to show system status!

### Step 6: Test Alerts

**Test that alerts work:**

1. Stop your API server (Ctrl+C)
2. Wait 5-10 minutes
3. You should receive email: "Monitor is DOWN"
4. Start API server again
5. Wait 5-10 minutes
6. You should receive email: "Monitor is UP"

---

## Part 3: Add Badges to README

Now let's add professional status badges to your README.

### Available Badges

**1. GitHub Actions (CI/CD)**
```markdown
![CI/CD](https://github.com/codewithtej1220/agent-observability-system/workflows/CI%2FCD/badge.svg)
```

**2. Python Version**
```markdown
![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
```

**3. PostgreSQL**
```markdown
![PostgreSQL](https://img.shields.io/badge/postgresql-13%2B-316192?logo=postgresql&logoColor=white)
```

**4. FastAPI**
```markdown
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
```

**5. License**
```markdown
![License](https://img.shields.io/badge/license-Private-red)
```

**6. Uptime (After UptimeRobot Setup)**

Find your monitor ID:
1. Go to UptimeRobot dashboard
2. Click on your monitor
3. Look at URL: `https://uptimerobot.com/dashboard#MONITOR_ID`
4. Copy the monitor ID (e.g., `m793053456`)

```markdown
![Uptime](https://img.shields.io/uptimerobot/ratio/7/m793053456?label=uptime)
```

**7. Response Time (UptimeRobot)**
```markdown
![Response Time](https://img.shields.io/uptimerobot/response/m793053456?label=response%20time)
```

### Where to Add Badges

I'll add them at the top of your README.md after the title.

---

## Verification Checklist

### Sentry Setup ✓
- [ ] Sentry account created
- [ ] Project created (Python/FastAPI)
- [ ] DSN added to `.env` file
- [ ] Sentry SDK installed (`pip install sentry-sdk[fastapi]`)
- [ ] API restarted and shows "Sentry enabled"
- [ ] Test error captured in Sentry dashboard

### UptimeRobot Setup ✓
- [ ] UptimeRobot account created
- [ ] Monitor added for `/health` endpoint
- [ ] Monitor added for `/stats` endpoint
- [ ] Email alerts configured
- [ ] Test alert received (optional)
- [ ] Status page created (optional)

### Badges ✓
- [ ] Identified which badges to add
- [ ] Monitor IDs obtained from UptimeRobot
- [ ] Ready to update README

---

## What Happens After Setup

### Sentry Will Automatically:
- ✅ Capture all unhandled exceptions
- ✅ Track API performance (response times)
- ✅ Send alerts for new errors
- ✅ Group similar errors together
- ✅ Show error trends over time

### UptimeRobot Will:
- ✅ Check your API every 5 minutes
- ✅ Alert you if API goes down
- ✅ Track uptime percentage
- ✅ Measure response times
- ✅ Show uptime history

### You Can:
- ✅ View real-time errors in Sentry dashboard
- ✅ Get instant alerts when something breaks
- ✅ See uptime stats in UptimeRobot
- ✅ Share status page with users
- ✅ Show professional badges on GitHub

---

## Costs

### Sentry (Free Tier)
- 5,000 errors/month
- 10,000 performance units/month
- 7-day error retention
- **Upgrade:** $29/month for 50K errors (if needed)

### UptimeRobot (Free Tier)
- 50 monitors
- 5-minute checks
- Unlimited alerts
- **Upgrade:** $7/month for 1-minute checks (if needed)

Both free tiers are **more than enough** for your project!

---

## Troubleshooting

### Sentry Not Working?
**Check:**
1. SENTRY_DSN in `.env` file is correct
2. Sentry SDK installed: `pip show sentry-sdk`
3. API restarted after adding DSN
4. Look for "Sentry enabled" message on startup

**Still not working?**
```bash
# Test Sentry manually
curl http://localhost:8001/sentry-debug
```

### UptimeRobot Not Working?
**Check:**
1. Your API has a **public URL** (not localhost)
2. URL is accessible: `curl https://your-url.com/health`
3. Monitor is active (not paused)
4. Alert contacts verified

### Badges Not Showing?
**Check:**
1. Monitor ID is correct
2. Repository visibility (badges work for private repos)
3. Wait a few minutes for badge cache to update

---

## Next Steps

Once monitoring is set up:

1. **I'll add badges to README** - Professional visual indicators
2. **Commit and push changes** - Update GitHub with monitoring
3. **Optional: Deploy to production** - Get public URL for UptimeRobot
4. **Move to Week 4** - Testing and optimization

**Ready to set up monitoring? Follow the steps above and let me know when you have:**
1. Sentry DSN (from Step 3)
2. Whether you want to use ngrok or deploy first for UptimeRobot
3. UptimeRobot monitor IDs (for badges)
