DOLCE EMPIRE v1.0.2 - Bothost /start fix

Fixes: FileNotFoundError: /app/data/catalog.json.
All 86 game cards are now packaged under dolce_empire/_catalog.json;
/app/data is reserved for the player database and may be mounted by the host.
Build validates bundled catalog before starting. No token changes.

HOW TO UPDATE YOUR GITHUB REPOSITORY:
1) Download this zip to Windows Downloads.
2) In PowerShell run:
   cd "$env:USERPROFILE\Downloads\dgemptestbot"
   Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\DolceEmpireBot_BOTHOST_FIX_v1.0.2.zip" -DestinationPath . -Force
   git add -A
   git commit -m "Fix Bothost missing catalog"
   git push origin main
3) Rebuild and restart the bot on Bothost.
4) Send /start in Telegram.

If build logs still show an old Dockerfile, force a new build from
GitHub main. This release also works with the earlier Dockerfile that
copies dolce_empire/ to /app/dolce_empire/.

Do not put your real Telegram token into git. Set BOT_TOKEN on Bothost.
Keep player DB persistent between rebuilds.
