# Running AI Study Agent on Vercel (portfolio preview)

The Flask deployment is a **non-persistent portfolio demo**, not a production learning-data service. Vercel Functions cannot write to the checked-out repository directory, so with `VERCEL=1`, SQLite and uploaded files are stored only in `/tmp/ai-study-agent`. This temporary filesystem is **not durable or shared reliably across instances**. New accounts, documents, quiz answers and notes can disappear between requests or deployments. Never enter sensitive information or upload real private study documents in this demo.

The local Windows/macOS/Linux app continues to use `data/study_agent.db` and `uploads/` without changing its storage paths. No local study data or database file is committed to GitHub or migrated to Vercel.

The Git-connected Vercel project needs `SECRET_KEY` (long random secret), `SESSION_COOKIE_SECURE=1` and `DEMO_ACCOUNT_ENABLED=0` as production environment variables. **Do not** add an actual Gemini API key to the public demo unless you are comfortable with usage costs and abuse risk. The app may return a helpful configuration error for AI functions without one. Full persistent, multi-user functionality requires an external database and object storage, with appropriate access controls; SQLite in `/tmp` is not a replacement.

To verify startup, open `/` (redirect to login) and `/login`. A Vercel deployment marked READY is not itself proof that the Flask request can complete; inspect runtime logs and run an HTTP smoke test before publishing the link in a CV.
