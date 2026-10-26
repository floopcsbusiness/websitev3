# Social stats auto-updater

Runs daily on GitHub Actions, pulls stats from YouTube, Instagram and TikTok, writes `stats.json`, and `index.html` displays it. You embed that page in your IONOS site.

Platforms with no credentials are skipped, so you can start with just YouTube (the easy one) and add the others later.

I wrote this from my knowledge of the APIs and could not test it against live accounts. Expect some tweaking, mostly around Instagram insight metrics and TikTok scopes. Check the Actions log after the first run.

## 1. Put it on GitHub

1. Create a new **public** GitHub repo (Pages is free for public repos).
2. Upload everything in this folder, keeping the `.github/workflows/` path.
3. Settings > Pages > deploy from the `main` branch, root folder.
4. Your dashboard will be at `https://YOUR_USERNAME.github.io/YOUR_REPO/`.

## 2. Get credentials

Add each one under Settings > Secrets and variables > Actions > New repository secret.

### YouTube (easy, no review)
1. Google Cloud Console: make a project, enable **YouTube Data API v3**.
2. Create an API key and restrict it to that API. Secret: `YT_API_KEY`.
3. Your channel ID (starts with `UC`) is in YouTube Studio > Settings > Channel > Advanced. Secret: `YT_CHANNEL_ID`.

### Instagram
1. The account must be a Professional (Business or Creator) account.
2. developers.facebook.com: make an app and add the **Instagram API with Instagram Login** product.
3. Add your Instagram account as a tester/role on the app.
4. Request the permissions `instagram_business_basic` and `instagram_business_manage_insights`.
5. Generate a token, exchange it for a **long-lived** token (60 days). Secret: `IG_ACCESS_TOKEN`.
6. The script refreshes the token on every run, so it stays alive as long as the job keeps running.

### TikTok (the slow one)
1. developers.tiktok.com: register an app, add **Login Kit** and **Display API**.
2. Request the scopes `user.info.basic`, `user.info.stats`, `video.list`.
3. TikTok reviews apps before they go live. Sandbox mode with your own account as a target user may let you skip review for your own stats, but I have not verified that.
4. Do the OAuth login once to get a **refresh token**: set your Login Kit redirect URI to `https://YOUR_USERNAME.github.io/YOUR_REPO/callback.html`, then run `python get_tiktok_token.py` on your own computer and follow the prompts.
5. Secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`.

### Optional but recommended: `GH_PAT`
Instagram and TikTok rotate tokens. To let the job save the new ones back into your secrets, create a fine-grained personal access token for this repo with **Secrets: read and write**, and save it as `GH_PAT`. Without it, you will have to update tokens by hand when they change.

## 3. Test it

Actions tab > "Update social stats" > Run workflow. Check the log. Each platform prints `ok`, `skipped`, or `FAILED` with a reason. A failed platform keeps its old numbers and shows "OUT OF DATE" on the dashboard instead of going blank.

## 4. Embed in IONOS

Add a custom HTML / code element (if your plan's editor has one) and paste:

```html
<iframe src="https://YOUR_USERNAME.github.io/YOUR_REPO/" width="100%" height="560" style="border:0" loading="lazy"></iframe>
```

## Notes

- Engagement = (likes + comments + shares) / views over the last 20 posts. YouTube has no shares in its API, so it uses likes and comments only. Say this somewhere if you show the numbers to sponsors.
- The repo is public, so `stats.json` is public. Secrets are not, but only put numbers in there you are fine showing anyone.
- GitHub can pause scheduled workflows on inactive repos, so glance at the Actions tab now and then.
- Change the run time in `.github/workflows/update-stats.yml` (cron is in UTC).
