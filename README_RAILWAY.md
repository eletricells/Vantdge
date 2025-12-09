# Vantdge on Railway - Complete Setup Guide

## 📋 What's Been Prepared

Your Vantdge application is fully configured and ready to deploy on Railway. Here's what's been done:

### ✅ Configuration Files
- **Procfile** - Backend startup command
- **Procfile.frontend** - Frontend startup command  
- **railway.toml** - Railway deployment settings
- **nixpacks.toml** - Build environment configuration
- **requirements.txt** - All Python dependencies

### ✅ Documentation Created
1. **QUICK_REFERENCE.md** ⭐ START HERE
2. **RAILWAY_QUICK_START.md** - 5-step deployment guide
3. **RAILWAY_DEPLOYMENT_GUIDE.md** - Detailed setup
4. **RAILWAY_SETUP_CHECKLIST.md** - Step-by-step checklist
5. **RAILWAY_TROUBLESHOOTING.md** - Problem solving
6. **DEPLOYMENT_SUMMARY.md** - Complete overview

---

## 🚀 Quick Start (15-20 minutes)

### Step 1: Set Backend Variables (5 min)
Railway Dashboard → **Vantdge - Backend** → **Variables**

Add these 6 variables:
```
ANTHROPIC_API_KEY=sk-ant-your-key
TAVILY_API_KEY=tvly-your-key
DATABASE_URL=postgresql://... (from Postgres service)
PYTHONUNBUFFERED=1
PORT=8000
PUBMED_API_KEY=your-key (optional)
```

### Step 2: Set Frontend Variables (3 min)
Railway Dashboard → **Vantdge - Frontend** → **Variables**

Add the same 6 variables, but change PORT to 8501

### Step 3: Connect Database (2 min)
1. Go to **Postgres** service → **Connect** tab
2. Copy connection string
3. Paste as DATABASE_URL in both services
4. Click "Connect to a new service" for each

### Step 4: Deploy (5-10 min)
- Push to GitHub (if using GitHub integration)
- Or: Service → Deployments → Deploy
- Wait for build to complete

### Step 5: Verify (2 min)
```bash
curl https://your-backend-url/health
curl https://your-backend-url/api/v1/status
Visit https://your-frontend-url
```

---

## 📊 Architecture

```
┌─────────────────────────────────────────┐
│         Railway Project                  │
├─────────────────────────────────────────┤
│                                          │
│  Backend (8000)    Frontend (8501)      │
│  FastAPI Server    Streamlit App        │
│  ├─ API Endpoints  ├─ UI Pages         │
│  ├─ Agents         ├─ Drug Browser     │
│  └─ Tools          └─ Case Studies     │
│         │                 │             │
│         └────────┬────────┘             │
│                  │                      │
│          PostgreSQL (5432)              │
│          ├─ Drug Database               │
│          ├─ Paper Catalog               │
│          └─ Case Studies                │
│                                          │
└─────────────────────────────────────────┘
```

---

## 🔑 Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| ANTHROPIC_API_KEY | Claude AI | sk-ant-... |
| TAVILY_API_KEY | Web search | tvly-... |
| DATABASE_URL | PostgreSQL | postgresql://... |
| PYTHONUNBUFFERED | Real-time logs | 1 |
| PORT | Service port | 8000 or 8501 |
| PUBMED_API_KEY | Literature | (optional) |

---

## ✨ Features

### Backend API
- ✅ FastAPI with async support
- ✅ CORS enabled
- ✅ Health check endpoint
- ✅ Status endpoint
- ✅ Drug analysis endpoint
- ✅ Prompt management API

### Frontend
- ✅ Streamlit UI
- ✅ Multiple pages
- ✅ Drug browser
- ✅ Case study analysis
- ✅ Literature search
- ✅ System diagnostics

### Database
- ✅ PostgreSQL online
- ✅ Multiple schemas
- ✅ Automatic backups
- ✅ Connection pooling

---

## 📁 Key Files

### Configuration
- `Procfile` - Backend startup
- `Procfile.frontend` - Frontend startup
- `railway.toml` - Railway config
- `nixpacks.toml` - Build config
- `requirements.txt` - Dependencies

### Application
- `src/api/main.py` - Backend API
- `frontend/Home.py` - Frontend entry
- `src/utils/config.py` - Settings

### Documentation
- `QUICK_REFERENCE.md` - Quick guide
- `RAILWAY_QUICK_START.md` - 5-step guide
- `RAILWAY_TROUBLESHOOTING.md` - Problem solving

---

## 🎯 Success Criteria

Your deployment is successful when:
1. ✅ Backend service shows "Online"
2. ✅ Frontend service shows "Online"
3. ✅ `/health` returns 200 OK
4. ✅ `/api/v1/status` shows configured
5. ✅ Frontend loads without errors
6. ✅ Frontend can call backend

---

## 🆘 Troubleshooting

**Service won't start?**
- Check logs: Service → Logs
- Verify env vars are set
- See RAILWAY_TROUBLESHOOTING.md

**Can't connect to database?**
- Copy fresh DATABASE_URL from Postgres
- Ensure Postgres service is Online
- Check connection string format

**Frontend won't load?**
- Verify backend is running
- Check backend URL is correct
- See RAILWAY_TROUBLESHOOTING.md

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| QUICK_REFERENCE.md | Quick lookup card |
| RAILWAY_QUICK_START.md | 5-step guide |
| RAILWAY_DEPLOYMENT_GUIDE.md | Detailed setup |
| RAILWAY_SETUP_CHECKLIST.md | Checklist |
| RAILWAY_TROUBLESHOOTING.md | Problem solving |
| DEPLOYMENT_SUMMARY.md | Full overview |

---

## 🔗 Useful Links

- Railway Dashboard: https://railway.app/dashboard
- FastAPI Docs: https://fastapi.tiangolo.com
- Streamlit Docs: https://docs.streamlit.io
- PostgreSQL Docs: https://postgresql.org/docs

---

## ⏱️ Timeline

- Step 1 (Env Vars): 5 min
- Step 2 (Env Vars): 3 min
- Step 3 (Database): 2 min
- Step 4 (Deploy): 5-10 min
- Step 5 (Verify): 2 min

**Total: 15-20 minutes**

---

## 💡 Pro Tips

1. **First deployment is slow** - Dependencies are built (5-10 min)
2. **Check logs first** - 90% of issues are visible there
3. **Use curl to test** - Verify endpoints work
4. **Keep API keys safe** - Never commit to git
5. **Monitor logs** - Watch for warnings

---

## 🎉 Ready to Deploy!

Everything is configured and ready. Follow the 4 steps above and your Vantdge platform will be live on Railway!

**Start with QUICK_REFERENCE.md for the fastest path to deployment.**

Good luck! 🚀

