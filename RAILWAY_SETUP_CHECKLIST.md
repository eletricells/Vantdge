# Railway Deployment Checklist

## Pre-Deployment ✅
- [x] Backend API configured (FastAPI)
- [x] Frontend configured (Streamlit)
- [x] Procfile created for backend
- [x] Procfile.frontend created
- [x] requirements.txt updated
- [x] nixpacks.toml configured
- [x] railway.toml configured

## Environment Variables Setup

### Backend Service
- [ ] Go to Vantdge - Backend → Variables
- [ ] Add `ANTHROPIC_API_KEY`
- [ ] Add `TAVILY_API_KEY`
- [ ] Add `PUBMED_API_KEY` (optional)
- [ ] Add `DATABASE_URL` (from Postgres service)
- [ ] Add `PYTHONUNBUFFERED=1`
- [ ] Add `PORT=8000`

### Frontend Service
- [ ] Go to Vantdge - Frontend → Variables
- [ ] Add `ANTHROPIC_API_KEY`
- [ ] Add `TAVILY_API_KEY`
- [ ] Add `PUBMED_API_KEY` (optional)
- [ ] Add `DATABASE_URL` (from Postgres service)
- [ ] Add `PYTHONUNBUFFERED=1`
- [ ] Add `PORT=8501`
- [ ] Add `BACKEND_URL=https://your-backend-url.up.railway.app`

## Database Connection

### Postgres Service
- [ ] Verify Postgres service is Online
- [ ] Copy connection string from Connect tab
- [ ] Add as `DATABASE_URL` to both services

### Link Services
- [ ] Connect Postgres to Backend service
- [ ] Connect Postgres to Frontend service

## Service Configuration

### Backend Service Settings
- [ ] Builder: Nixpacks
- [ ] Root Directory: `/`
- [ ] Health Check Path: `/health`
- [ ] Health Check Timeout: 300 seconds
- [ ] Restart Policy: on_failure

### Frontend Service Settings
- [ ] Builder: Nixpacks
- [ ] Root Directory: `/`
- [ ] Health Check Path: `/`
- [ ] Health Check Timeout: 300 seconds
- [ ] Restart Policy: on_failure

## Deployment

### Initial Deploy
- [ ] Push code to GitHub (if using GitHub integration)
- [ ] Or manually trigger deployment in Railway
- [ ] Monitor build logs for errors
- [ ] Wait for services to start

### Verification
- [ ] Backend health check: `curl https://your-backend-url/health`
- [ ] Frontend loads: Visit `https://your-frontend-url`
- [ ] Status endpoint: `curl https://your-backend-url/api/v1/status`
- [ ] Check all environment variables are loaded

## Post-Deployment

### Testing
- [ ] Test backend API endpoints
- [ ] Test frontend pages load
- [ ] Test database connectivity
- [ ] Check logs for any errors

### Monitoring
- [ ] Set up log monitoring
- [ ] Configure alerts (optional)
- [ ] Monitor resource usage
- [ ] Check for any warnings

## Troubleshooting

If services don't start:
1. [ ] Check deployment logs
2. [ ] Verify all environment variables are set
3. [ ] Check database connection string
4. [ ] Verify API keys are valid
5. [ ] Check requirements.txt for missing dependencies

## Notes

- First deployment takes 5-10 minutes (building dependencies)
- Subsequent deployments are faster (2-3 minutes)
- Logs are available in Deployments → View Logs
- Services auto-restart on failure
- Database persists across deployments

## Quick Links

- Railway Dashboard: https://railway.app/dashboard
- Backend Health: https://your-backend-url/health
- Frontend: https://your-frontend-url
- API Status: https://your-backend-url/api/v1/status

