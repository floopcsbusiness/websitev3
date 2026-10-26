"""One-time helper: gets your TikTok refresh token.

Run this on your own computer (NOT in GitHub Actions):

    pip install requests
    python get_tiktok_token.py

It prints a link. Open it, log in with your TikTok account, approve the
permissions, and you land on callback.html which shows a code. Paste that
code back here and the script prints your refresh token.
"""
import getpass
import secrets
import sys
from urllib.parse import urlencode

import requests

SCOPES = "user.info.basic,user.info.stats,video.list"


def main():
    print("TikTok one-time token helper\n")
    client_key = input("Client key: ").strip()
    client_secret = getpass.getpass("Client secret (hidden as you type): ").strip()
    redirect_uri = input("Redirect URI (your GitHub Pages callback.html URL): ").strip()

    params = {
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": secrets.token_urlsafe(8),
    }
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)
    print("\nOpen this link in your browser and approve access:\n")
    print(url)
    print("\nAfter approving you will land on your callback page. Copy the code it shows.")
    print("The code expires quickly, so paste it right away.\n")
    code = input("Code: ").strip()

    r = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = r.json()
    if "refresh_token" not in data:
        print("\nTikTok said no:")
        print(data.get("error_description") or data)
        sys.exit(1)

    granted = data.get("scope", "")
    print("\nSuccess. Save this as the GitHub secret TIKTOK_REFRESH_TOKEN:\n")
    print(data["refresh_token"])
    print("\nScopes granted:", granted)
    if "user.info.stats" not in granted:
        print("\nWARNING: user.info.stats was not granted, so follower counts will be missing.")
        print("Check that the scope is added to your app and approved or enabled for sandbox.")
    print("\nRefresh tokens last about a year. Treat it like a password.")


if __name__ == "__main__":
    main()
