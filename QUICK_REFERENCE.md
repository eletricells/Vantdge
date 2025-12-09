# Vantdge Railway - Quick Reference Card

## 🚀 4-Step Deployment

### Step 1️⃣: Backend Environment Variables
```
Service: Vantdge - Backend
Tab: Variables

ANTHROPIC_API_KEY = sk-ant-...
TAVILY_API_KEY = tvly-...
DATABASE_URL = postgresql://...
PYTHONUNBUFFERED = 1
PORT = 8000
PUBMED_API_KEY = (optional)
```

### Step 2️⃣: Frontend Environment Variables
```
Service: Vantdge - Frontend
Tab: Variables

ANTHROPIC_API_KEY = sk-ant-...
TAVILY_API_KEY = tvly-...
DATABASE_URL = postgresql://...
PYTHONUNBUFFERED = 1
PORT = 8501
PUBMED_API_KEY = (optional)
```

### Step 3️⃣: Connect Database
```
Service: Postgres
Tab: Connect

1. Copy connection string
2. Go to Backend → Variables → DATABASE_URL
3. Paste connection string
4. Go to Frontend → Variables → DATABASE_URL
5. Paste connection string
6. Click "Connect to a new service" for each
```

### Step 4️⃣: Deploy
```
Option A: GitHub Integration
- Push code to GitHub
- Railway auto-deploys

Option B: Manual Deploy
- Service → Deployments → Deploy
- Wait 5-10 minutes
- Check logs for errors
```

---

## ✅ Verification Checklist

After deployment, verify:

```bash
# 1. Backend Health
curl https://your-backend-url/health
# Expected: {"status":"healthy","version":"1.0.0"}

# 2. API Status
curl https://your-backend-url/api/v1/status
# Expected: {"status":"running","anthropic_configured":true,...}

# 3. Frontend
Visit: https://your-frontend-url
# Expected: Streamlit app loads

# 4. Database
Check backend logs for "Database connected"
```

---

## 🔑 Environment Variables

| Name | Backend | Frontend | Required |
|------|---------|----------|----------|
| ANTHROPIC_API_KEY | ✅ | ✅ | YES |
| TAVILY_API_KEY | ✅ | ✅ | Recommended |
| DATABASE_URL | ✅ | ✅ | YES |
| PYTHONUNBUFFERED | ✅ | ✅ | YES |
| PORT | 8000 | 8501 | YES |
| PUBMED_API_KEY | ✅ | ✅ | Optional |

---

## 📍 Important URLs

```
Backend Health:    https://your-backend-url/health
API Status:        https://your-backend-url/api/v1/status
Frontend:          https://your-frontend-url
Railway Dashboard: https://railway.app/dashboard
```

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Service won't start | Check logs, verify env vars |
| Can't connect DB | Copy fresh DATABASE_URL |
| Frontend blank | Check backend is running |
| API 404 error | Check endpoint path (/api/v1/) |
| Slow deployment | Normal first time (5-10 min) |

---

## 📚 Documentation Files

- **RAILWAY_QUICK_START.md** - Detailed 5-step guide
- **RAILWAY_DEPLOYMENT_GUIDE.md** - Complete setup guide
- **RAILWAY_TROUBLESHOOTING.md** - Problem solving
- **DEPLOYMENT_SUMMARY.md** - Full overview

---

## 🎯 Success Indicators

✅ Backend service: Online  
✅ Frontend service: Online  
✅ Postgres service: Online  
✅ /health returns 200  
✅ /api/v1/status shows configured  
✅ Frontend loads without errors  

---

## ⏱️ Timeline

- Step 1: 5 minutes
- Step 2: 3 minutes
- Step 3: 2 minutes
- Step 4: 5-10 minutes
- Verification: 2 minutes

**Total: 15-20 minutes**

---

## 🔗 Useful Links

- Railway: https://railway.app
- FastAPI: https://fastapi.tiangolo.com
- Streamlit: https://streamlit.io
- PostgreSQL: https://postgresql.org

---

## 💡 Pro Tips

1. **First deployment is slow** - Dependencies are being built
2. **Check logs first** - 90% of issues are visible there
3. **Use curl to test** - Verify endpoints work
4. **Keep API keys safe** - Never commit to git
5. **Monitor logs** - Watch for warnings

---

## 🎉 You're Ready!

Everything is configured. Follow the 4 steps and you'll be live in 15-20 minutes!

Questions? Check the documentation files or Railway logs.

