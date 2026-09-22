# Setup

Two parts: a one-time Google Cloud setup that only you can do (about 10 minutes), then one install command.

## 1. Google Cloud project

Sweep asks for the full Gmail scope (`https://mail.google.com/`), which Google restricts. That means every copy of Sweep needs its own Google Cloud project, with you listed as a test user. Nobody else's project can grant it to you.

1. Open https://console.cloud.google.com and create a new project. Name it anything, for example `sweep`.
2. **APIs & Services → Library**. Enable **Gmail API** and **Google Drive API**. (Drive is only used to read your storage quota. Skip it and the gauge falls back to message counts.)
3. **APIs & Services → Google Auth Platform** (Google's current name for the OAuth consent screen). If it asks you to configure the app first, click through. Then use the left sidebar:
   - **Branding**: App name `Sweep`, support email and developer contact set to your own address.
   - **Audience**: User type **External**. Leave publishing status as **Testing**. Under **Test users → Add users**, add your Gmail address.
   - **Data Access → Add or remove scopes**. Paste these into the "Manually add scopes" box, then **Update** and **Save**:
     ```
     https://mail.google.com/
     https://www.googleapis.com/auth/drive.metadata.readonly
     https://www.googleapis.com/auth/userinfo.email
     openid
     ```
   - **Clients → Create client**. Application type **Desktop app**. Copy the client ID and client secret. For a Desktop app client, Google does not treat the secret as confidential.

   The Settings page in that sidebar is not needed.

## 2. Install and run

Requires Python 3.11 or newer. Pick one:

```bash
# from a clone (works today)
git clone https://github.com/griffinsisk/sweep && cd sweep/backend
uv tool install .

# uv, from the release wheel (once a v* tag has been pushed)
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
