"""Ye script apne PC par EK BAAR chalao (GitHub par nahi).
pip install google-auth-oauthlib
Pehle client_secret.json isi folder me rakho (Google Cloud -> OAuth client 'Desktop app')."""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json", scopes=["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
cfg = json.load(open("client_secret.json"))
c = cfg.get("installed") or cfg.get("web")
print("\n=== In 3 values ko GitHub Secrets me daalo ===")
print("YT_CLIENT_ID     =", c["client_id"])
print("YT_CLIENT_SECRET =", c["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
