# Linking vantdge.com to Railway - Complete Guide

## 🎯 Overview

You'll be setting up your custom domain `vantdge.com` to point to your Railway services. You'll need to:
1. Add the domain in Railway
2. Update DNS records at your domain registrar
3. Verify the connection

---

## 📋 Step-by-Step Setup

### Step 1: Add Custom Domain in Railway (Frontend)

**In the Railway Dashboard:**

1. Go to **Vantdge - Frontend** service
2. Click **Networking** tab
3. Under "Public Networking" → "Add Custom Domain"
4. Enter: `vantdge.com` (or `www.vantdge.com` for the frontend)
5. Select port: **443** (HTTPS)
6. Click **"Add Domain"**

**Railway will show you:**
- A target domain (something like `vantdge-frontend-production.up.railway.app`)
- Instructions to update your DNS

---

### Step 2: Add Custom Domain in Railway (Backend)

**In the Railway Dashboard:**

1. Go to **Vantdge - Backend** service
2. Click **Networking** tab
3. Under "Public Networking" → "Add Custom Domain"
4. Enter: `api.vantdge.com` (for the backend API)
5. Select port: **443** (HTTPS)
6. Click **"Add Domain"**

**Railway will show you:**
- A target domain for the backend
- Instructions to update your DNS

---

### Step 3: Update DNS Records at Your Registrar

**You need to add CNAME records:**

#### For Frontend (www.vantdge.com)
```
Type: CNAME
Name: www
Value: vantdge-frontend-production.up.railway.app
TTL: 3600 (or default)
```

#### For Backend (api.vantdge.com)
```
Type: CNAME
Name: api
Value: vantdge-backend-production.up.railway.app
TTL: 3600 (or default)
```

#### For Root Domain (vantdge.com)
```
Type: CNAME or ALIAS
Name: @ (or leave blank)
Value: vantdge-frontend-production.up.railway.app
TTL: 3600 (or default)
```

**Note:** Some registrars use ALIAS instead of CNAME for root domain. Check your registrar's documentation.

---

## 🔧 How to Update DNS Records

### If you use GoDaddy:
1. Log in to GoDaddy
2. Go to **Domains** → **Your Domain** → **DNS**
3. Find "CNAME Records" section
4. Click **"Add"**
5. Enter the Name and Value from above
6. Click **"Save"**

### If you use Namecheap:
1. Log in to Namecheap
2. Go to **Domain List** → **Manage** (your domain)
3. Click **"Advanced DNS"** tab
4. Find "Host Records" section
5. Click **"Add New Record"**
6. Select Type: **CNAME**
7. Enter Name and Value from above
8. Click **"Save All Changes"**

### If you use Route 53 (AWS):
1. Log in to AWS Route 53
2. Go to **Hosted Zones** → Your domain
3. Click **"Create Record"**
4. Select Type: **CNAME**
5. Enter Name and Value from above
6. Click **"Create Records"**

### If you use Cloudflare:
1. Log in to Cloudflare
2. Go to your domain → **DNS**
3. Click **"Add record"**
4. Select Type: **CNAME**
5. Enter Name and Value from above
6. Click **"Save"**

---

## ⏱️ DNS Propagation

After updating DNS records:
- **Immediate**: Changes are made at your registrar
- **5-30 minutes**: Most DNS servers update
- **Up to 48 hours**: Full global propagation

**You can check propagation here:**
- https://www.whatsmydns.net/
- Enter your domain (vantdge.com)
- Check if it resolves to Railway's servers

---

## ✅ Verification Steps

### 1. Check DNS Records
```bash
# On Windows PowerShell:
nslookup vantdge.com
nslookup api.vantdge.com
nslookup www.vantdge.com

# Should show Railway's servers
```

### 2. Test Frontend
```bash
curl https://vantdge.com
# Should return Streamlit app HTML
```

### 3. Test Backend
```bash
curl https://api.vantdge.com/health
# Should return: {"status":"healthy"}
```

### 4. Visit in Browser
- Frontend: https://vantdge.com
- Backend API: https://api.vantdge.com/api/v1/status

---

## 🆘 Troubleshooting

### Domain shows "Not Found"
- **Cause**: DNS hasn't propagated yet
- **Solution**: Wait 5-30 minutes and try again
- **Check**: Use https://www.whatsmydns.net/

### SSL Certificate Error
- **Cause**: Railway is still provisioning the certificate
- **Solution**: Wait 5-10 minutes for Railway to issue the certificate
- **Check**: Railway Dashboard → Service → Networking → Domain status

### Backend can't reach API
- **Cause**: Frontend doesn't know the new API URL
- **Solution**: Update BACKEND_URL environment variable
  - Frontend service → Variables
  - Set: `BACKEND_URL=https://api.vantdge.com`
  - Redeploy

### CNAME Record Conflict
- **Cause**: You already have an A record for the domain
- **Solution**: Delete the A record and use CNAME instead
- **Note**: Some registrars require ALIAS for root domain

---

## 📊 DNS Record Summary

| Subdomain | Type | Value | Purpose |
|-----------|------|-------|---------|
| @ (root) | CNAME/ALIAS | vantdge-frontend-production.up.railway.app | Frontend |
| www | CNAME | vantdge-frontend-production.up.railway.app | Frontend |
| api | CNAME | vantdge-backend-production.up.railway.app | Backend API |

---

## 🎯 Final Checklist

- [ ] Added custom domain in Railway Frontend service
- [ ] Added custom domain in Railway Backend service
- [ ] Updated DNS records at registrar
- [ ] Waited for DNS propagation (5-30 min)
- [ ] Verified DNS with nslookup or whatsmydns.net
- [ ] Tested frontend: https://vantdge.com
- [ ] Tested backend: https://api.vantdge.com/health
- [ ] Updated BACKEND_URL in frontend environment variables
- [ ] Frontend can reach backend API

---

## 💡 Pro Tips

1. **Use subdomains** - api.vantdge.com for backend, www.vantdge.com for frontend
2. **Keep TTL low** - Set to 300-600 during setup for faster changes
3. **Monitor logs** - Check Railway logs for any SSL certificate issues
4. **Test early** - Don't wait for full propagation to test
5. **Update environment variables** - Frontend needs to know the new API URL

---

## 🔗 Useful Links

- Railway Networking Docs: https://docs.railway.app/deploy/networking
- DNS Propagation Checker: https://www.whatsmydns.net/
- SSL Certificate Status: Check in Railway Dashboard → Service → Networking

---

## 📞 Need Help?

If you get stuck:
1. Check Railway logs for SSL certificate errors
2. Verify DNS records with nslookup
3. Wait for DNS propagation (up to 48 hours)
4. Check that CNAME records point to correct Railway domains
5. Ensure BACKEND_URL is updated in frontend environment variables

