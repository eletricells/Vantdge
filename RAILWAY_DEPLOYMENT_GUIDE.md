# Vantdge Railway Deployment Guide

## Overview
This guide walks you through deploying Vantdge on Railway with:
- **Backend**: FastAPI server (Python)
- **Frontend**: Streamlit app (Python)
- **Database**: PostgreSQL

## Current Status
✅ PostgreSQL is online
✅ Backend service created
✅ Frontend service deploying
✅ Configuration files ready

---

## Step 1: Set Up Environment Variables

### For Backend Service
1. Go to Railway Dashboard → **Vantdge - Backend** service
2. Click the **Variables** tab
3. Add these environment variables:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
TAVILY_API_KEY=tvly-your-key-here
PUBMED_API_KEY=your-pubmed-key-here
PYTHONUNBUFFERED=1
PORT=8000
```

**Optional variables:**
```
BRAVE_API_KEY=your-brave-key-here
CLINICALTRIALS_API_KEY=your-key-here
SEMANTIC_SCHOLAR_API_KEY=your-key-here
```

### For Frontend Service
1. Go to Railway Dashboard → **Vantdge - Frontend** service
2. Click the **Variables** tab
3. Add the same environment variables as backend:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
TAVILY_API_KEY=tvly-your-key-here
PUBMED_API_KEY=your-pubmed-key-here
PYTHONUNBUFFERED=1
PORT=8501
```

### Database Connection String
1. Click on the **Postgres** service
2. Go to **Connect** tab
3. Copy the connection string under "Postgres Connection URL"
4. Add to both services as `DATABASE_URL`:

```
DATABASE_URL=postgresql://user:password@host:port/database
```

---

## Step 2: Configure Backend Service

### Procfile Configuration
The backend uses this Procfile (already created):

```
web: python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### In Railway Dashboard:
1. Go to **Vantdge - Backend** service
2. Click **Settings** tab
3. Under "Build", ensure:
   - **Builder**: Nixpacks (or Dockerfile)
   - **Root Directory**: `/` (root of repo)
4. Under "Deploy", set:
   - **Start Command**: Leave empty (uses Procfile)
   - **Health Check Path**: `/health`
   - **Health Check Timeout**: 300 seconds

---

## Step 3: Configure Frontend Service

### Procfile Configuration
The frontend uses this Procfile:

```
web: streamlit run frontend/Home.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true
```

### In Railway Dashboard:
1. Go to **Vantdge - Frontend** service
2. Click **Settings** tab
3. Under "Build", ensure:
   - **Builder**: Nixpacks
   - **Root Directory**: `/` (root of repo)
4. Under "Deploy", set:
   - **Start Command**: Leave empty (uses Procfile)
   - **Health Check Path**: `/` (Streamlit doesn't have /health)
   - **Health Check Timeout**: 300 seconds

---

## Step 4: Connect Services

### Link Database to Services
1. Go to **Postgres** service
2. Click **Connect** tab
3. For each service (Backend & Frontend):
   - Click "Connect to a new service"
   - Select the service
   - The `DATABASE_URL` will be automatically injected

### Link Backend to Frontend
1. Go to **Vantdge - Frontend** service
2. Click **Variables** tab
3. Add:
   ```
   BACKEND_URL=https://vantdge-backend-production.up.railway.app
   ```
   (Replace with your actual backend URL from Railway)

---

## Step 5: Deploy

### Initial Deployment
1. Push your code to GitHub (if using GitHub integration)
2. Railway will automatically detect changes and redeploy
3. Or manually trigger deployment:
   - Go to service → **Deployments** tab
   - Click **Deploy** button

### Monitor Deployment
1. Go to **Deployments** tab
2. Watch the build logs
3. Check for any errors in the logs

---

## Step 6: Verify Deployment

### Test Backend
```bash
curl https://your-backend-url.up.railway.app/health
```

Expected response:
```json
{"status": "healthy", "version": "1.0.0"}
```

### Test Frontend
Visit: `https://your-frontend-url.up.railway.app`

### Check Status Endpoint
```bash
curl https://your-backend-url.up.railway.app/api/v1/status
```

Expected response:
```json
{
  "status": "running",
  "anthropic_configured": true,
  "tavily_configured": true,
  "database_configured": true
}
```

---

## Troubleshooting

### Backend won't start
1. Check logs: **Deployments** → **View Logs**
2. Common issues:
   - Missing `ANTHROPIC_API_KEY` environment variable
   - Database connection string incorrect
   - Port already in use (shouldn't happen on Railway)

### Frontend won't load
1. Check logs for Streamlit errors
2. Ensure `BACKEND_URL` is set correctly
3. Check CORS configuration in backend

### Database connection fails
1. Verify `DATABASE_URL` is set
2. Check Postgres service is online
3. Ensure database exists and is accessible

### Slow deployments
- First deployment takes longer (building dependencies)
- Subsequent deployments are faster
- Check build logs for any warnings

---

## Environment Variables Reference

### Required
- `ANTHROPIC_API_KEY`: Your Anthropic API key

### Optional but Recommended
- `TAVILY_API_KEY`: For web search functionality
- `PUBMED_API_KEY`: For PubMed literature search
- `DATABASE_URL`: PostgreSQL connection string

### Optional
- `BRAVE_API_KEY`: Alternative web search
- `CLINICALTRIALS_API_KEY`: Clinical trials data
- `SEMANTIC_SCHOLAR_API_KEY`: Academic paper search

### System
- `PYTHONUNBUFFERED=1`: Ensures logs appear in real-time
- `PORT`: Service port (8000 for backend, 8501 for frontend)

---

## Next Steps

1. ✅ Set environment variables in Railway
2. ✅ Verify services are running
3. ✅ Test API endpoints
4. ✅ Test frontend connectivity
5. Configure custom domain (optional)
6. Set up monitoring and alerts (optional)

---

## Support

For issues:
1. Check Railway logs: **Deployments** → **View Logs**
2. Check application logs in the service
3. Verify all environment variables are set
4. Ensure database is online and accessible

