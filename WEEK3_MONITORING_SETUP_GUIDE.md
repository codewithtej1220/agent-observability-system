# Week 3: Monitoring Setup Guide (Sentry + UptimeRobot + Badges)

**Current Status:** GitHub setup complete ✅  
**Next Steps:** Error monitoring, uptime monitoring, and status badges

---

## Task 1: Sentry Error Monitoring Setup

### Why Sentry?
- Real-time error tracking with stack traces
- Performance monitoring for API endpoints
- Automatic error grouping and alerts
- Production-grade debugging

### Step-by-Step Setup

#### 1. Create Sentry Account
1. Go to: https://sentry.io/signup/
2. Sign up (free tier includes 5,000 errors/month)
3. Create organization (use your GitHub username or project name)

#### 2. Create Sentry Project
1. Click "Create Project"
2. Select platform: **Python**
3. Framework: **FastAPI**
4. Project name: `agent-observability-system`
5. Click "Create Project"

#### 3. Get Your DSN
After project creation, Sentry will show your DSN:
```
https://abc123def456@o123456.ingest.sentry.io/7890123
```
**Copy this DSN - you'll need it next!**

#### 4. Add DSN to Environment
Edit your `.env` file:
```bash
# Add this line
SENTRY_DSN=https://abc123def456@o123456.ingest.sentry.io/7890123
```

#### 5. Install Sentry SDK
```bash
pip install sentry-sdk[fastapi]
```

#### 6. I'll Update Your Code
Let me know when you have the DSN, and I'll integrate Sentry into `api/main.py`:
- Automatic error capturing
- Performance tracing
- User context tracking
- Release tracking

#### 7. Test Sentry Integration
After integration, I'll add a test endpoint to trigger an error:
```bash
curl -X GET http://localhost:8001/test-sentry-error
```
Then check your Sentry dashboard for the captured error!

---

## Task 2: UptimeRobot Monitoring Setup

### Why UptimeRobot?
- 24/7 uptime monitoring (free for 50 monitors)
- Alerts via email/SMS/Slack
- Response time tracking
- Public status page option

### Step-by-Step Setup

#### 1. Create UptimeRobot Account
1. Go to: https://uptimerobot.com/signUp
2. Sign up (free plan includes 50 monitors, 5-minute checks)
3. Verify email

#### 2. Add HTTP Monitor for API
1. Click "Add New Monitor"
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** Agent Observability API
4. **URL:** Your deployed API URL + `/health`
   - Example: `https://your-domain.com/health`
   - For now: Use localhost tunnel (ngrok) if not deployed yet
5. **Monitoring Interval:** 5 minutes
6. Click "Create Monitor"

#### 3. Add Monitor for Frontend
1. Click "Add New Monitor"
2. **Monitor Type:** HTTP(s)
3. **Friendly Name:** Agent Observability Dashboard
4. **URL:** Your deployed frontend URL
   - Example: `https://your-domain.com`
5. **Monitoring Interval:** 5 minutes
6. Click "Create Monitor"

#### 4. Set Up Alerts
1. Go to "My Settings" → "Alert Contacts"
2. Add email address
3. Configure alert preferences:
   - Alert when: Monitor goes DOWN
   - Alert when: Monitor comes back UP
   - Repeat alerts: Every 60 minutes

#### 5. Optional: Public Status Page
1. Go to "Public Status Pages"
2. Click "Add New Status Page"
3. Select monitors to display
4. Customize branding
5. Get public URL to share

### Note About Deployment
UptimeRobot needs a **public URL** to monitor. Options:
- **Deployed:** Use your production URL
- **Local Testing:** Use ngrok tunnel temporarily
  ```bash
  ngrok http 8001
  # Use the ngrok URL in UptimeRobot
  ```

---

## Task 3: Add README Badges

### Available Badges

#### 1. GitHub Actions Build Status
```markdown
![CI/CD](https://github.com/codewithtej1220/agent-observability-system/workflows/CI%2FCD/badge.svg)
```

#### 2. Python Version
```markdown
![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
```

#### 3. PostgreSQL Version
```markdown
![PostgreSQL](https://img.shields.io/badge/postgresql-13%2B-316192?logo=postgresql&logoColor=white)
```

#### 4. FastAPI Framework
```markdown
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)
```

#### 5. License (Private)
```markdown
![License](https://img.shields.io/badge/license-Private-red)
```

#### 6. React Version
```markdown
![React](https://img.shields.io/badge/React-18.x-61DAFB?logo=react&logoColor=white)
```

#### 7. Uptime (After UptimeRobot Setup)
```markdown
![Uptime](https://img.shields.io/uptimerobot/ratio/7/m123456789-abc123)
```
*Replace `m123456789-abc123` with your monitor ID from UptimeRobot*

### Where to Add Badges
Add them at the top of `README.md`, right after the title:

```markdown
# Agent Observability System

![CI/CD](https://github.com/codewithtej1220/agent-observability-system/workflows/CI%2FCD/badge.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/postgresql-13%2B-316192?logo=postgresql&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18.x-61DAFB?logo=react&logoColor=white)
![License](https://img.shields.io/badge/license-Private-red)

An AI system for detecting silent failures in LLM agent pipelines...
```

---

## Task 4: GitHub Actions Verification

### Check if CI/CD Ran Successfully

1. **Go to Actions Tab:**
   https://github.com/codewithtej1220/agent-observability-system/actions

2. **Look for Workflow Runs:**
   - Should see "CI/CD" workflow
   - Check status: ✅ Success or ❌ Failed

3. **If Failed, Review Logs:**
   - Click on the failed run
   - Review error messages
   - Common issues:
     - Missing dependencies
     - Python version mismatch
     - Test failures

4. **Fix Issues:**
   - Update `.github/workflows/ci-cd.yml` if needed
   - Commit and push changes
   - Workflow will run again automatically

---

## Quick Checklist

### Before You Start
- [ ] Backend API running locally (port 8001)
- [ ] Frontend running locally (port 3000)
- [ ] PostgreSQL connected and working
- [ ] `.env` file configured

### Sentry Setup
- [ ] Sentry account created
- [ ] Project created (Python/FastAPI)
- [ ] DSN copied
- [ ] DSN added to `.env`
- [ ] Ready for code integration

### UptimeRobot Setup
- [ ] UptimeRobot account created
- [ ] Have deployment URL (or ngrok tunnel)
- [ ] Monitors configured
- [ ] Alerts set up

### Badges
- [ ] Identified which badges to add
- [ ] Ready to update README

### GitHub Actions
- [ ] Checked Actions tab
- [ ] Verified workflow status
- [ ] Addressed any issues

---

## What I'll Do Next

Once you provide:
1. **Sentry DSN** - I'll integrate error monitoring into the API
2. **Deployment status** - I'll help set up UptimeRobot
3. **Badge preferences** - I'll add them to README

Then I'll:
1. Update `api/main.py` with Sentry integration
2. Add Sentry test endpoint
3. Update `requirements.txt` with sentry-sdk
4. Add badges to README
5. Update Week 3 documentation
6. Commit and push all changes

---

## Estimated Time

- **Sentry Setup:** 10 minutes (account + integration)
- **UptimeRobot Setup:** 10 minutes (account + monitors)
- **Badges:** 5 minutes (copy/paste into README)
- **Testing:** 10 minutes (verify everything works)

**Total:** ~35 minutes

---

## Optional: Deploy to Production

If you want to deploy to make UptimeRobot fully functional:

### Quick Deploy Options:

#### 1. Railway (Easiest)
- Free tier available
- Connect GitHub repo
- Auto-deploy on push
- Provides public URL
- https://railway.app

#### 2. Render
- Free tier for web services
- PostgreSQL included
- Connect GitHub repo
- https://render.com

#### 3. Heroku
- Classic platform
- Free tier available
- Easy PostgreSQL setup
- https://heroku.com

#### 4. DigitalOcean App Platform
- $5/month minimum
- More control
- Good performance
- https://digitalocean.com

**Let me know if you want deployment help!**

---

## Next Steps

**Tell me when you're ready to:**
1. Set up Sentry (provide DSN)
2. Set up UptimeRobot (provide deployment URL or use ngrok)
3. Add badges to README

**Or if you want to:**
- Deploy to production first
- Skip monitoring for now and move to Week 4 (testing)
- Focus on specific monitoring tool only

---

## Current Week 3 Progress

✅ **Completed:**
- GitHub repository created and configured
- Code pushed with proper .gitignore
- Professional README
- CI/CD workflow configured

🔄 **In Progress:**
- Sentry error monitoring setup
- UptimeRobot uptime monitoring
- README badges

📋 **Upcoming (Week 4):**
- Comprehensive test suite
- Load testing
- Performance optimization
- Final documentation

---

**Ready to continue? Let me know!**
