# Google Calendar Integration Setup Guide

## Quick Setup Steps

### Step 1: Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** → **New Project**
3. Name it: `DecisionOS` (or any name)
4. Click **Create**

### Step 2: Enable Calendar API
1. In your project, go to **APIs & Services** → **Library**
2. Search for "Google Calendar API"
3. Click on it → Click **Enable**

### Step 3: Configure OAuth Consent Screen
1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** → Click **Create**
3. Fill in:
   - App name: `DecisionOS`
   - User support email: Your email
   - Developer contact: Your email
4. Click **Save and Continue**
5. Skip Scopes → Click **Save and Continue**
6. Add Test Users → Add your Gmail address
7. Click **Save and Continue**

### Step 4: Create OAuth Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Application type: **Web application**
4. Name: `DecisionOS Web`
5. Add **Authorized redirect URIs**:
   - `http://localhost`
   - `http://localhost:8000/api/calendar/oauth/callback`
   - `https://decisionos-837202638935.asia-south1.run.app/api/calendar/oauth/callback`
6. Click **Create**
7. Click **Download JSON**
8. Rename downloaded file to `credentials.json`
9. Move it to: `D:\Development\Projects\AI\DecisionOs\credentials.json`

Important: the JSON must contain a top-level `web` object (not `installed`) for Cloud Run OAuth redirect flows.

### Step 4B: Cloud Run Secret Setup (Production)
1. Open the downloaded OAuth JSON file
2. Base64-encode it (or keep as plain JSON)
3. Set Cloud Run environment variable:
   - `GOOGLE_CREDENTIALS_JSON=<json-or-base64-json>`
4. Redeploy the service

### Step 5: Authenticate
1. Start the DecisionOS server
2. Open browser: `http://127.0.0.1:8000/api/calendar/auth`
3. Sign in with your Google account
4. Grant calendar permissions
5. Token will be saved automatically

## After Setup

Once authenticated, DecisionOS will:
- Fetch events from your Google Calendar
- Create/update/delete events via MCP tools
- Sync events to local database as backup

## Troubleshooting

### "Access blocked" error
- Make sure you added your email as a test user in OAuth consent screen

### "Credentials not found"
- Verify `credentials.json` is at: `D:\Development\Projects\AI\DecisionOs\credentials.json`
- For Cloud Run, verify `GOOGLE_CREDENTIALS_JSON` is configured on the service

### Token expired
- Delete `token.json` and re-authenticate via `/api/calendar/auth`

### `redirect_uri_mismatch`
- Ensure both local and production callback URLs are listed in the OAuth client:
   - `http://localhost`
   - `http://localhost:8000/api/calendar/oauth/callback`
   - `https://decisionos-837202638935.asia-south1.run.app/api/calendar/oauth/callback`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/calendar/status` | Check integration status |
| `GET /api/calendar/auth` | Trigger OAuth flow |
| `GET /api/calendar/events` | Get events (Google or DB) |

## Production Smoke Test

Run:

```bash
.venv\Scripts\python.exe smoke_test_calendar_prod.py
```

Strict mode (must already be authenticated):

```bash
set DECISIONOS_REQUIRE_AUTH=1
set DECISIONOS_USER_ID=your_user_id
.venv\Scripts\python.exe smoke_test_calendar_prod.py
```
