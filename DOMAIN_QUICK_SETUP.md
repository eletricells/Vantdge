# vantdge.com Setup - Quick Reference

## 🚀 3-Step Setup (10 minutes)

### Step 1: Add Domain in Railway (Frontend)
```
Railway Dashboard → Vantdge - Frontend → Networking
→ Add Custom Domain
→ Enter: vantdge.com
→ Port: 443
→ Click "Add Domain"

Railway shows you the target domain (copy this!)
Example: vantdge-frontend-production.up.railway.app
```

### Step 2: Add Domain in Railway (Backend)
```
Railway Dashboard → Vantdge - Backend → Networking
→ Add Custom Domain
→ Enter: api.vantdge.com
→ Port: 443
→ Click "Add Domain"

Railway shows you the target domain (copy this!)
Example: vantdge-backend-production.up.railway.app
```

### Step 3: Update DNS at Your Registrar

**Add these CNAME records:**

```
Record 1 (Root Domain):
Type: CNAME or ALIAS
Name: @ (or leave blank)
Value: vantdge-frontend-production.up.railway.app

Record 2 (WWW):
Type: CNAME
Name: www
Value: vantdge-frontend-production.up.railway.app

Record 3 (API):
Type: CNAME
Name: api
Value: vantdge-backend-production.up.railway.app
```

---

## 🔧 Where to Update DNS

**GoDaddy:**
- Domains → Your Domain → DNS → CNAME Records → Add

**Namecheap:**
- Domain List → Manage → Advanced DNS → Host Records → Add

**Route 53 (AWS):**
- Hosted Zones → Your Domain → Create Record

**Cloudflare:**
- Your Domain → DNS → Add Record

---

## ⏱️ Wait for DNS Propagation

- **5-30 minutes**: Most servers update
- **Up to 48 hours**: Full global propagation
- **Check status**: https://www.whatsmydns.net/

---

## ✅ Verify It Works

```bash
# Test DNS
nslookup vantdge.com
nslookup api.vantdge.com

# Test Frontend
curl https://vantdge.com

# Test Backend
curl https://api.vantdge.com/health
```

---

## 🎯 Update Frontend Environment Variables

After DNS is set up, update the frontend:

```
Railway Dashboard → Vantdge - Frontend → Variables

Change:
BACKEND_URL = https://api.vantdge.com

Then redeploy the frontend service
```

---

## 🎉 Done!

Your domain is now linked:
- Frontend: https://vantdge.com
- Backend API: https://api.vantdge.com
- Status: https://api.vantdge.com/api/v1/status

---

## 🆘 If It Doesn't Work

1. **Check DNS propagation** - https://www.whatsmydns.net/
2. **Check Railway logs** - Look for SSL certificate errors
3. **Wait longer** - DNS can take up to 48 hours
4. **Verify CNAME records** - Make sure they point to Railway domains
5. **Update BACKEND_URL** - Frontend needs to know the new API URL

See CUSTOM_DOMAIN_SETUP.md for detailed troubleshooting.

