# First-run setup

One-time Google Cloud setup, then local dev. ~15 minutes.

## 1. Google Cloud project

1. https://console.cloud.google.com → New project → name it `sweep`
2. **APIs & Services → Library** → enable **Gmail API** and **Google Drive API**
3. **APIs & Services → OAuth consent screen**
   - User type: **External**
   - App name: Sweep. Support email: yours. Developer contact: yours
   - Scopes → Add: `gmail.modify`, `drive.metadata.readonly`, `userinfo.email`, `openid`
   - **Test users → Add** your Gmail address (and anyone else who'll use it). Up to 100. Leave publishing status as **Testing**
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/auth/callback`
   - Copy the client ID and secret

## 2. Environment

```bash
cp .env.example backend/.env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # → SESSION_SECRET
```

Fill in `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, and `ANTHROPIC_API_KEY`.

## 3. Run

```bash
# terminal 1
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# terminal 2
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 → Sign in with Google → you'll see the "unverified app" screen → Advanced → Go to Sweep → Allow.

## 4. First real run (measure it!)

1. Note the storage number on the gauge
2. Count → Trash all on **Everything before 2020**
3. Empty trash
4. Note the new storage number and how long it took — that's the headline for the README

## Deploying

- **Backend**: `backend/Dockerfile` runs anywhere (Fly.io, Render, Railway). Set all env vars; set `COOKIE_SECURE=true` and `FRONTEND_ORIGIN` to your frontend URL
- **Frontend**: `npm run build` → deploy `dist/` (Vercel, Netlify, Cloudflare Pages). Set `VITE_API_BASE` to the backend URL at build time
- Add the production callback URL (`https://api.yourdomain/auth/callback`) to the OAuth client
- Because the cookie is `SameSite=Lax`, host frontend and backend on the same registrable domain (e.g. `sweep.example.com` + `api.sweep.example.com`) or switch to `SameSite=None; Secure`
