# Setup

Two parts: a one-time Google Cloud setup that only you can do (about 10 minutes), then one install command.

## 1. Google Cloud project

Sweep asks for the `gmail.modify` scope, which Google restricts. That means every copy of Sweep needs its own Google Cloud project, with you listed as a test user. Nobody else's project can grant it to you.

1. Open https://console.cloud.google.com and create a new project. Name it anything, for example `sweep`.
2. **APIs & Services → Library**. Enable **Gmail API** and **Google Drive API**. (Drive is only used to read your storage quota. Skip it and the gauge falls back to message counts.)
3. **APIs & Services → OAuth consent screen**
   - User type: **External**
   - App name: Sweep. Support email and developer contact: your own address.
   - Scopes → Add: `gmail.modify`, `drive.metadata.readonly`, `userinfo.email`, `openid`
   - **Test users → Add** your Gmail address. Leave the publishing status as **Testing**.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Copy the client ID and client secret. For a Desktop app client, Google does not treat the secret as confidential.

## 2. Install and run

Requires Python 3.11 or newer. Pick one:

```bash
# uv (recommended)
uv tool install https://github.com/griffinsisk/sweep/releases/latest/download/sweep_gmail-0.2.0-py3-none-any.whl

# pipx
pipx install https://github.com/griffinsisk/sweep/releases/latest/download/sweep_gmail-0.2.0-py3-none-any.whl
```

Then, from any folder:

```bash
export GOOGLE_CLIENT_ID=...apps.googleusercontent.com
export GOOGLE_CLIENT_SECRET=...
sweep
```

Or put those two lines in a `.env` file in the folder you run `sweep` from. Your browser opens at http://127.0.0.1:8000. Sign in with Google. You will see an "unverified app" warning because the project is in Testing mode. Choose **Advanced → Go to Sweep → Allow**.

To enable the "Ask Claude what to do" button, also set `ANTHROPIC_API_KEY`. Everything else works without it.

## 3. First real run

1. Note the storage number on the gauge.
2. **Count**, then **Trash all** on "Everything before 2020".
3. **Empty trash**.
4. Note the new storage number and how long it took.

## Developing

```bash
git clone https://github.com/griffinsisk/sweep && cd sweep
cp .env.example backend/.env    # fill in the two Google values

# terminal 1: API on :8000
cd backend && pip install -e ".[dev]" && FRONTEND_ORIGIN=http://localhost:5173 uvicorn sweep.main:app --reload

# terminal 2: Vite dev server on :5173, proxies /api and /auth to :8000
cd frontend && npm install && npm run dev
```

`npm run build` writes the compiled frontend into `backend/sweep/static/`, and `python -m build --wheel` in `backend/` packages it. CI does both on every push and attaches the wheel to a GitHub Release on every `v*` tag.
