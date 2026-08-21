# Sentry Setup Instructions - Quick Guide

Your code is already integrated! Just follow these 5 simple steps:

---

## Step 1: Create Sentry Account (2 minutes)

1. Go to: **https://sentry.io/signup/**
2. Click **"Sign up with GitHub"** (easiest option)
3. Or use email signup
4. Choose **"Developer"** plan (Free)
   - 5,000 errors/month
   - 10,000 performance units/month
   - Perfect for your project!

---

## Step 2: Create Project (1 minute)

After signing up, Sentry will ask you to create a project:

1. **Platform:** Select **"Python"**
2. **Framework:** Select **"FastAPI"** (or skip if not shown)
3. **Project Name:** `agent-observability-system`
4. **Alert Frequency:** Leave as "On every new issue" (default)
5. Click **"Create Project"**

---

## Step 3: Get Your DSN (30 seconds)

After creating the project, Sentry will show you a setup page with your DSN:

**Example DSN:**
```
https://abc123def456@o123456.ingest.sentry.io/7890123
```

**Copy this entire DSN!** You'll need it in the next step.

**Note:** Your DSN will be different - don't use the example above!

---

## Step 4: Add DSN to Your .env File (30 seconds)

1. Open your `.env` file (in the project root directory)
2. Find the line that says:
   ```bash
   # SENTRY_DSN=https://abc123def456@o123456.ingest.sentry.io/7890123
   ```
3. **Uncomment it** (remove the `#`) and **replace with YOUR DSN:**
   ```bash
   SENTRY_DSN=https://YOUR-ACTUAL-DSN-HERE@o123456.ingest.sentry.io/7890123
   ```

**Your .env file should now look like:**
```bash
DATABASE_URL=postgresql://postgres:DVkp4ZH97AsM1Dpi@db.xjdlvkhtfceyulhqpgmj.supabase.co:5432/postgres
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
SENTRY_DSN=https://YOUR-ACTUAL-DSN@o123456.ingest.sentry.io/7890123
ARTIFACTS_DIR=artifacts
```

**Save the file!**

---

## Step 5: Restart Your API & Test (2 minutes)

### Restart API:
```bash
# Stop your current API if running (Ctrl+C)

# Make sure virtual environment is activated
.\venv\Scripts\activate

# Start API again
uvicorn api.main:app --reload --port 8001
```

**You should see:**
```
✅ Sentry error monitoring enabled
INFO:     Uvicorn running on http://127.0.0.1:8001
```

If you see that ✅ message, Sentry is working!

---

### Test Error Capture:

**Test 1: Trigger a test error**
```bash
curl http://localhost:8001/sentry-debug
```

**Test 2: Check Sentry Dashboard**
1. Go to: https://sentry.io
2. Click on your project: `agent-observability-system`
3. Click **"Issues"** in the left sidebar
4. You should see a **ZeroDivisionError** captured! 🎉

**Example of what you'll see:**
- Error type: `ZeroDivisionError: division by zero`
- Location: `api/main.py` in `/sentry-debug` endpoint
- Stack trace with full context
- Request details (URL, method, headers)
- Server info (Python version, OS)

---

## Verification Checklist

- [ ] Sentry account created
- [ ] Project created (Python/FastAPI)
- [ ] DSN copied
- [ ] DSN added to `.env` file (uncommented and replaced)
- [ ] API restarted
- [ ] Saw "✅ Sentry error monitoring enabled" message
- [ ] Test error sent to Sentry
- [ ] Error appears in Sentry dashboard

---

## What Sentry Will Do Now

**Automatic Error Capturing:**
- ✅ All Python exceptions
- ✅ Unhandled errors
- ✅ API endpoint errors
- ✅ Database errors
- ✅ Stack traces with full context

**Performance Monitoring:**
- ✅ Slow API endpoints
- ✅ Database query times
- ✅ External API calls
- ✅ Transaction traces

**Alerts:**
- 📧 Email when new errors occur
- 📧 Email for error spikes
- 📧 Weekly summary reports

---

## Troubleshooting

### Issue: Don't see "Sentry enabled" message

**Check:**
1. Is SENTRY_DSN uncommented in `.env`? (no `#` at start)
2. Is the DSN correct? (copy-paste from Sentry)
3. Did you restart the API after adding DSN?

**Fix:**
```bash
# Check your .env file
cat .env | grep SENTRY

# Should show (without #):
# SENTRY_DSN=https://...
```

---

### Issue: Sentry SDK not installed

**Error message:**
```
⚠️  Sentry SDK not installed. Run: pip install sentry-sdk
```

**Fix:**
```bash
pip install sentry-sdk[fastapi]
```

---

### Issue: Test error not showing in Sentry

**Check:**
1. Did you see the error response from curl?
2. Wait 10-30 seconds for Sentry to process
3. Refresh Sentry dashboard
4. Check "Issues" tab (not "Performance")

---

## Production Configuration

For production, update your `.env`:

```bash
ENVIRONMENT=production
SENTRY_DSN=https://your-dsn-here@o123456.ingest.sentry.io/7890123
```

Sentry will automatically:
- Tag errors with `environment: production`
- Enable release tracking
- Provide production-specific insights

---

## What Happens After Setup

**Every time an error occurs in your API:**

1. **Sentry captures it automatically** 📸
2. **Logs full stack trace** 📝
3. **Records request context** 🔍
4. **Groups similar errors** 📊
5. **Sends you an email alert** 📧
6. **Shows trends over time** 📈

**You'll see in Sentry:**
- Which endpoints are failing
- What errors users encounter
- When errors started happening
- How many users are affected
- Performance bottlenecks

---

## Cost

**Free Tier (Developer):**
- 5,000 errors/month
- 10,000 performance units/month
- 7-day data retention
- Unlimited projects
- **Perfect for your project!**

If you exceed limits, Sentry just stops capturing new errors for the month (your app keeps running fine).

---

## Next Steps After Sentry Setup

Once Sentry is working:

1. **Commit the changes** (we'll do this together)
2. **Update README** with Sentry badge (optional)
3. **Deploy to production** (optional)
4. **Monitor real errors** 🎯

---

## Ready?

**Follow the 5 steps above, then let me know your DSN, and I'll help you commit everything!**

The code is already integrated - you just need the DSN! 🚀
