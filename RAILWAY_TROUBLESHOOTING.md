# Railway Deployment Troubleshooting Guide

## Common Issues & Solutions

### 1. Backend Service Won't Start

**Symptoms:**
- Service shows "Crashed" status
- Logs show errors on startup

**Solutions:**

**Missing Environment Variables**
```
Error: anthropic_api_key is required
```
- Go to Backend service → Variables
- Add `ANTHROPIC_API_KEY=your-key`
- Redeploy

**Database Connection Failed**
```
Error: could not connect to server
```
- Verify `DATABASE_URL` is set correctly
- Check Postgres service is Online
- Copy fresh connection string from Postgres → Connect tab
- Ensure database exists

**Port Already in Use**
```
Error: Address already in use
```
- Railway handles this automatically
- Check if PORT variable is set to 8000
- Restart service

**Missing Dependencies**
```
Error: ModuleNotFoundError
```
- Check requirements.txt has all dependencies
- Rebuild service (Deployments → Rebuild)

---

### 2. Frontend Service Won't Load

**Symptoms:**
- Page shows error or blank
- Streamlit won't start

**Solutions:**

**Backend Not Reachable**
```
Error: Connection refused
```
- Verify backend is running
- Check `BACKEND_URL` environment variable
- Ensure CORS is enabled in backend (it is by default)

**Streamlit Configuration Issue**
```
Error: streamlit run failed
```
- Check PORT is set to 8501
- Verify `PYTHONUNBUFFERED=1` is set
- Check logs for specific errors

**Missing Dependencies**
```
Error: ModuleNotFoundError: No module named 'streamlit'
```
- Rebuild service
- Check requirements.txt includes streamlit

---

### 3. Database Connection Issues

**Symptoms:**
- Backend can't connect to database
- Queries fail with connection errors

**Solutions:**

**Wrong Connection String**
```
Error: FATAL: password authentication failed
```
- Get fresh connection string from Postgres → Connect tab
- Ensure no typos in DATABASE_URL
- Check special characters are URL-encoded

**Database Doesn't Exist**
```
Error: database "vantdge" does not exist
```
- Create database in Postgres
- Or use default database name from connection string

**Postgres Service Offline**
```
Error: could not translate host name
```
- Check Postgres service status in Railway
- Restart Postgres service if needed
- Wait for it to come back online

**Connection Pool Exhausted**
```
Error: QueuePool limit exceeded
```
- Reduce max connections in SQLAlchemy
- Restart service to clear connections
- Check for connection leaks in code

---

### 4. API Endpoints Not Working

**Symptoms:**
- 404 errors on API calls
- 500 internal server errors

**Solutions:**

**Endpoint Not Found**
```
Error: 404 Not Found
```
- Verify endpoint path is correct
- Check backend is running
- Ensure API version is correct (/api/v1/)

**Internal Server Error**
```
Error: 500 Internal Server Error
```
- Check backend logs for details
- Verify all environment variables are set
- Check database is accessible

**CORS Issues**
```
Error: CORS policy blocked request
```
- Backend has CORS enabled by default
- Check frontend is making requests to correct URL
- Verify `BACKEND_URL` is set in frontend

---

### 5. Slow Deployments

**Symptoms:**
- Deployment takes 10+ minutes
- Build seems stuck

**Solutions:**

**First Deployment is Slow**
- Normal: 5-10 minutes for first build
- Subsequent builds: 2-3 minutes
- Dependencies are cached after first build

**Large Dependencies**
- Some packages (PyMuPDF, camelot) take time to build
- This is normal
- Subsequent deployments are faster

**Check Build Progress**
- Go to Deployments → View Logs
- Look for "Building" or "Installing" messages
- Don't cancel unless truly stuck (>20 min)

---

### 6. Environment Variables Not Loading

**Symptoms:**
- Settings show None for API keys
- Features disabled unexpectedly

**Solutions:**

**Variables Not Set**
- Go to service → Variables tab
- Verify all required variables are present
- Check for typos in variable names
- Redeploy after adding variables

**Variables Not Reloading**
- Restart service: Service → Settings → Restart
- Or redeploy: Deployments → Redeploy

**Check What's Loaded**
- Call `/api/v1/status` endpoint
- Shows which features are configured
- Helps identify missing variables

---

### 7. Logs Not Showing

**Symptoms:**
- Can't see deployment logs
- Logs are empty

**Solutions:**

**View Deployment Logs**
1. Go to service → Deployments
2. Click on deployment
3. Click "View Logs"
4. Scroll to see all messages

**View Runtime Logs**
1. Go to service → Logs tab
2. Shows real-time application logs
3. Filter by time or search

**Enable Debug Logging**
- Set `LOG_LEVEL=DEBUG` in variables
- Redeploy
- More detailed logs will appear

---

### 8. Service Keeps Restarting

**Symptoms:**
- Service crashes and restarts repeatedly
- Deployment shows "Restarting"

**Solutions:**

**Check Restart Policy**
- Service → Settings → Deploy
- Restart Policy: on_failure
- Max Retries: 3
- This is normal behavior

**Find Root Cause**
- Check logs for error messages
- Look for patterns in crashes
- Common causes:
  - Out of memory
  - Database connection lost
  - Unhandled exception

**Increase Resources**
- Service → Settings → Resources
- Increase RAM if needed
- Restart service

---

## Debugging Tips

### 1. Check Service Status
```
Railway Dashboard → Service → Status
```
Shows: Online, Crashed, Building, etc.

### 2. View Logs
```
Service → Logs tab (real-time)
Service → Deployments → View Logs (build logs)
```

### 3. Test Endpoints
```bash
# Health check
curl https://your-backend-url/health

# Status
curl https://your-backend-url/api/v1/status

# With verbose output
curl -v https://your-backend-url/health
```

### 4. Check Environment Variables
```bash
# In logs, look for:
# "Settings loaded successfully"
# "Configuration error"
```

### 5. Database Connection Test
```bash
# From backend logs, should see:
# "Database connected"
# Or error message if failed
```

---

## Getting Help

1. **Check Logs First**
   - 90% of issues are visible in logs
   - Service → Logs or Deployments → View Logs

2. **Verify Environment Variables**
   - Service → Variables
   - Ensure all required variables are set

3. **Test Endpoints**
   - Use curl or Postman
   - Test /health and /api/v1/status

4. **Check Railway Status**
   - https://status.railway.app
   - See if there are platform issues

5. **Review Configuration**
   - Verify Procfile is correct
   - Check requirements.txt has all dependencies
   - Ensure railway.toml is valid

---

## Quick Reference

| Issue | Check | Fix |
|-------|-------|-----|
| Won't start | Logs | Add missing env vars |
| Can't connect DB | DATABASE_URL | Copy from Postgres |
| API 404 | Endpoint path | Check /api/v1/ prefix |
| Slow build | First deploy? | Normal, wait 5-10 min |
| Keeps crashing | Logs | Fix root cause error |
| Blank frontend | Backend URL | Set BACKEND_URL var |

