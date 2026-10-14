# SmartEvent — Phase 4 Starter

A runnable Phase 4 implementation scaffold for the SmartEvent project using **FastAPI + SQLite + React/Vite**.

## Included modules
- **18 — Live ticket availability:** WebSocket broadcast and booking endpoint with a conditional availability check.
- **19 — Recommendations:** category/location/popularity scoring based on bookings and event activity; trending list.
- **20 — Wishlist:** add, remove, and list saved events, scoped to the authenticated user.
- **21 — Event updates:** create and list event announcements.
- **22 — Profile:** view/update profile, booking summary, optional profile picture upload endpoint.
- **23 — Advanced search:** category, price, date, location, text search and sorting by date/price/popularity.
- **24 — Chat assistant:** chat endpoint with intent-based event discovery, trending and booking-count help. This is a local rule-based assistant, not an external LLM integration.

## Requirements
- Python 3.10+
- Node.js 18+

## 1. Run the backend (Windows PowerShell)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Backend: http://127.0.0.1:8000  
Interactive API docs: http://127.0.0.1:8000/docs

On macOS/Linux activate with `source .venv/bin/activate`.

## 2. Add sample events
Open http://127.0.0.1:8000/docs, find `POST /api/demo/seed`, and click **Try it out → Execute**. This adds sample events.

## 3. Run the frontend (second terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open the local URL printed by Vite (usually http://localhost:5173).

## 4. Try it
1. Create an account with an email and password (minimum 8 characters).
2. Browse/search events and save events with the heart icon.
3. Book a ticket and watch the live available count update.
4. Open Recommended, Trending, Wishlist, Profile, and the floating assistant.
5. Use API docs to post event updates or create new events.

## API summary
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register and receive JWT |
| POST | `/api/auth/login` | Login and receive JWT |
| GET | `/api/events` | Search/filter/sort events |
| GET | `/api/events/{id}` | Event detail and view tracking |
| POST | `/api/events` | Create event (demo auth policy) |
| POST | `/api/events/{id}/book?quantity=1` | Book tickets |
| GET | `/api/bookings/me` | Current user's bookings |
| GET | `/api/recommendations` | Personalized event suggestions |
| GET | `/api/events/trending` | Trending events |
| GET/POST/DELETE | `/api/wishlist[/{event_id}]` | Manage wishlist |
| GET/POST | `/api/events/{id}/updates` | Event announcements |
| GET/PUT | `/api/profile` | Read/update profile |
| POST | `/api/profile/picture` | Upload profile picture |
| POST | `/api/chat` | Assistant interaction |
| WS | `/ws/availability` | Live ticket updates |
| POST | `/api/demo/seed` | Add sample events |

## Important production notes
This is a learning/demo scaffold, not a production-ready ticketing platform.
- Set a strong random `SECRET_KEY` in the environment and never commit real secrets.
- Implement role-based authorization and event ownership checks before allowing organizers/admins to create events or post announcements. The starter marks these demo policies in code.
- For multi-worker or multi-server WebSocket broadcasts, use Redis Pub/Sub or a message broker; this in-memory manager only broadcasts within one process.
- SQLite is fine for local learning. For high concurrency, use PostgreSQL with transactions/row-level locking and a database-specific atomic inventory update. Test booking concurrency before production.
- For a real AI chatbot, replace the rule-based `/api/chat` logic with your chosen AI provider and keep API keys server-side in environment variables.
- Profile-picture uploads should be size-limited and stored on object storage in production. Add static file serving/CDN as appropriate.
- Add tests, rate limiting, audit logs, payment integration checks, and stronger authorization before deployment.
