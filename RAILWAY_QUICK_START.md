# Vantdge Railway Deployment - Quick Start

## What You Have
✅ PostgreSQL database online  
✅ Backend service created  
✅ Frontend service deploying  
✅ All configuration files ready  

## What You Need to Do (5 Steps)

### Step 1: Get Your Database Connection String (2 min)
1. Open Railway Dashboard
2. Click **Postgres** service
3. Go to **Connect** tab
4. Copy the connection string (looks like: `postgresql://user:pass@host:port/db`)

### Step 2: Set Backend Environment Variables (3 min)
1. Click **Vantdge - Backend** service
2. Go to **Variables** tab
3. Add these 6 variables:
   - `ANTHROPIC_API_KEY` = your Anthropic key
   - `TAVILY_API_KEY` = your Tavily key
   - `DATABASE_URL` = paste from Step 1
   - `PYTHONUNBUFFERED` = 1
   - `PORT` = 8000
   - `PUBMED_API_KEY` = your PubMed key (optional)

### Step 3: Set Frontend Environment Variables (3 min)
1. Click **Vantdge - Frontend** service
2. Go to **Variables** tab
3. Add the same 6 variables as Step 2
4. Change `PORT` to 8501

### Step 4: Connect Database to Services (2 min)
1. Click **Postgres** service
2. Go to **Connect** tab
3. Click "Connect to a new service"
4. Select **Vantdge - Backend** → confirm
5. Repeat for **Vantdge - Frontend**

### Step 5: Deploy (5-10 min)
1. Push code to GitHub (if using GitHub integration)
2. Or go to service → **Deployments** → click **Deploy**
3. Wait for build to complete
4. Check logs for any errors

## Verify It Works

### Test Backend
```bash
curl https://your-backend-url.up.railway.app/health
```
Should return: `{"status":"healthy","version":"1.0.0"}`

### Test Frontend
Visit: `https://your-frontend-url.up.railway.app`

### Check Status
```bash
curl https://your-backend-url.up.railway.app/api/v1/status
```

## Environment Variables Explained

| Variable | Purpose | Example |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude AI access | sk-ant-... |
| `TAVILY_API_KEY` | Web search | tvly-... |
| `DATABASE_URL` | PostgreSQL connection | postgresql://... |
| `PYTHONUNBUFFERED` | Real-time logs | 1 |
| `PORT` | Service port | 8000 or 8501 |
| `PUBMED_API_KEY` | Literature search | (optional) |

## Troubleshooting

**Backend won't start?**
- Check logs: Deployments → View Logs
- Verify `ANTHROPIC_API_KEY` is set
- Check `DATABASE_URL` is correct

**Frontend won't load?**
- Check Streamlit logs
- Verify backend is running
- Check `BACKEND_URL` if needed

**Database connection fails?**
- Verify `DATABASE_URL` is set
- Check Postgres service is Online
- Ensure database exists

## Files Created/Updated

- ✅ `Procfile` - Backend startup command
- ✅ `Procfile.backend` - Updated with python -m
- ✅ `Procfile.frontend` - Frontend startup command
- ✅ `railway.toml` - Railway configuration
- ✅ `nixpacks.toml` - Build configuration
- ✅ `requirements.txt` - Python dependencies

## Next Steps

1. Follow the 5 steps above
2. Monitor deployment logs
3. Test endpoints
4. Set up monitoring (optional)
5. Configure custom domain (optional)

## Support

- Railway Docs: https://docs.railway.app
- Check logs: Service → Deployments → View Logs
- Common issues: See RAILWAY_DEPLOYMENT_GUIDE.md

