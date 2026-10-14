from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_, update
from typing import Optional
from pathlib import Path
import shutil, re

from .database import Base, engine, get_db
from .models import User, Event, Booking, Wishlist, EventUpdate
from .schemas import RegisterIn, LoginIn, EventIn, ProfileIn, ChatIn
from .security import hash_password, verify_password, create_token, token_user_id

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SmartEvent Phase 4 API", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ConnectionManager:
    def __init__(self): self.connections = []
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.connections.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.connections: self.connections.remove(ws)
    async def broadcast(self, message: dict):
        dead = []
        for ws in self.connections:
            try: await ws.send_json(message)
            except Exception: dead.append(ws)
        for ws in dead: self.disconnect(ws)

manager = ConnectionManager()

def current_user(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    try: uid = token_user_id(authorization.split(" ", 1)[1])
    except ValueError: raise HTTPException(401, "Invalid or expired token")
    user = db.query(User).filter(User.id == uid).first()
    if not user: raise HTTPException(401, "User not found")
    return user

def event_dict(e, db):
    return {"id": e.id, "title": e.title, "description": e.description, "category": e.category,
            "location": e.location, "date": e.date, "price": e.price,
            "total_tickets": e.total_tickets, "tickets_sold": e.tickets_sold,
            "available_tickets": max(0, e.total_tickets-e.tickets_sold), "views": e.views,
            "popularity": e.tickets_sold + e.views}

@app.get("/")
def root(): return {"message": "SmartEvent Phase 4 API is running", "docs": "/docs"}

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email.lower()).first(): raise HTTPException(409, "Email already registered")
    user = User(name=data.name, email=data.email.lower(), password_hash=hash_password(data.password), location=data.location)
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email}}

@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Incorrect email or password")
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email}}

@app.get("/api/events")
def list_events(category: Optional[str] = None, min_price: Optional[int] = None, max_price: Optional[int] = None,
                start_date: Optional[str] = None, end_date: Optional[str] = None, location: Optional[str] = None,
                search: Optional[str] = None, sort_by: str = "date", db: Session = Depends(get_db)):
    q = db.query(Event).filter(Event.is_active == True)
    if category: q = q.filter(Event.category.ilike(f"%{category}%"))
    if min_price is not None: q = q.filter(Event.price >= min_price)
    if max_price is not None: q = q.filter(Event.price <= max_price)
    if start_date: q = q.filter(Event.date >= start_date)
    if end_date: q = q.filter(Event.date <= end_date)
    if location: q = q.filter(Event.location.ilike(f"%{location}%"))
    if search: q = q.filter(or_(Event.title.ilike(f"%{search}%"), Event.description.ilike(f"%{search}%")))
    events = q.all()
    if sort_by == "price": events.sort(key=lambda e: e.price)
    elif sort_by == "popularity": events.sort(key=lambda e: e.tickets_sold + e.views, reverse=True)
    else: events.sort(key=lambda e: e.date)
    return [event_dict(e, db) for e in events]

@app.get("/api/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    e = db.query(Event).filter(Event.id == event_id, Event.is_active == True).first()
    if not e: raise HTTPException(404, "Event not found")
    e.views += 1; db.commit()
    return event_dict(e, db)

@app.post("/api/events")
def create_event(data: EventIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Demo policy: authenticated users may create events. Add organizer/admin roles for production.
    e = Event(**data.model_dump()); db.add(e); db.commit(); db.refresh(e)
    return event_dict(e, db)

@app.post("/api/events/{event_id}/book")
async def book_event(event_id: int, quantity: int = 1, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if quantity < 1 or quantity > 10: raise HTTPException(400, "Quantity must be between 1 and 10")
    e = db.query(Event).filter(Event.id == event_id, Event.is_active == True).with_for_update().first()
    if not e: raise HTTPException(404, "Event not found")
    # Conditional update is the key overbooking guard. SQLite serializes writes; use a DB with row locks for production scale.
    result = db.query(Event).filter(Event.id == event_id, Event.tickets_sold + quantity <= Event.total_tickets).update({Event.tickets_sold: Event.tickets_sold + quantity}, synchronize_session=False)
    if result != 1:
        db.rollback(); raise HTTPException(409, "Not enough tickets available")
    booking = Booking(user_id=user.id, event_id=event_id, quantity=quantity)
    db.add(booking); db.commit(); db.refresh(booking); db.refresh(e)
    await manager.broadcast({"type": "availability", "event_id": event_id, "available_tickets": max(0, e.total_tickets-e.tickets_sold), "tickets_sold": e.tickets_sold})
    return {"message": "Booking successful", "booking_id": booking.id, "event_id": event_id, "quantity": quantity, "available_tickets": max(0, e.total_tickets-e.tickets_sold)}

@app.get("/api/bookings/me")
def my_bookings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Booking).filter(Booking.user_id == user.id).order_by(Booking.id.desc()).all()
    return [{"id": b.id, "event": event_dict(db.query(Event).get(b.event_id), db), "quantity": b.quantity, "created_at": str(b.created_at)} for b in rows if db.query(Event).get(b.event_id)]

@app.get("/api/recommendations")
def recommendations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    booked_ids = [b.event_id for b in db.query(Booking).filter(Booking.user_id == user.id).all()]
    cats = [e.category for e in db.query(Event).filter(Event.id.in_(booked_ids)).all()] if booked_ids else []
    q = db.query(Event).filter(Event.is_active == True)
    events = [e for e in q.all() if e.id not in booked_ids]
    events.sort(key=lambda e: (2 if e.category in cats else 0) + (1 if user.location and user.location.lower() in e.location.lower() else 0) + e.tickets_sold + e.views, reverse=True)
    return [event_dict(e, db) for e in events[:10]]

@app.get("/api/events/trending")
def trending(db: Session = Depends(get_db)):
    events = db.query(Event).filter(Event.is_active == True).all()
    events.sort(key=lambda e: e.tickets_sold + e.views, reverse=True)
    return [event_dict(e, db) for e in events[:10]]

@app.get("/api/wishlist")
def get_wishlist(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Wishlist).filter(Wishlist.user_id == user.id).all()
    return [event_dict(e, db) for w in rows if (e := db.query(Event).filter(Event.id == w.event_id).first())]

@app.post("/api/wishlist/{event_id}")
def add_wishlist(event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.query(Event).filter(Event.id == event_id).first(): raise HTTPException(404, "Event not found")
    if db.query(Wishlist).filter_by(user_id=user.id, event_id=event_id).first(): return {"message": "Already saved"}
    db.add(Wishlist(user_id=user.id, event_id=event_id)); db.commit()
    return {"message": "Event saved to wishlist"}

@app.delete("/api/wishlist/{event_id}")
def remove_wishlist(event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Wishlist).filter_by(user_id=user.id, event_id=event_id).first()
    if not row: raise HTTPException(404, "Wishlist item not found")
    db.delete(row); db.commit(); return {"message": "Removed from wishlist"}

@app.post("/api/events/{event_id}/updates")
def post_update(event_id: int, message: str, important: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.query(Event).filter(Event.id == event_id).first(): raise HTTPException(404, "Event not found")
    # Demo policy: authenticated users can post. Restrict to event owner/organizer/admin in production.
    row = EventUpdate(event_id=event_id, message=message[:2000], important=important)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "event_id": row.event_id, "message": row.message, "important": row.important, "created_at": str(row.created_at)}

@app.get("/api/events/{event_id}/updates")
def get_updates(event_id: int, db: Session = Depends(get_db)):
    return [{"id": u.id, "message": u.message, "important": u.important, "created_at": str(u.created_at)} for u in db.query(EventUpdate).filter(EventUpdate.event_id == event_id).order_by(EventUpdate.id.desc()).all()]

@app.get("/api/profile")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    bookings = db.query(Booking).filter(Booking.user_id == user.id).all()
    return {"id": user.id, "name": user.name, "email": user.email, "location": user.location, "profile_picture": user.profile_picture,
            "booking_count": len(bookings), "tickets_booked": sum(b.quantity for b in bookings), "wishlist_count": db.query(Wishlist).filter(Wishlist.user_id == user.id).count()}

@app.put("/api/profile")
def update_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.name = data.name; user.location = data.location; user.profile_picture = data.profile_picture
    db.commit(); db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email, "location": user.location, "profile_picture": user.profile_picture}

@app.post("/api/profile/picture")
def upload_picture(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"): raise HTTPException(400, "Upload a JPG, PNG, or WEBP image")
    if file.size and file.size > 3 * 1024 * 1024: raise HTTPException(413, "Image must be 3 MB or smaller")
    folder = Path("uploads"); folder.mkdir(exist_ok=True)
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    path = folder / f"user_{user.id}{suffix}"
    with path.open("wb") as out: shutil.copyfileobj(file.file, out)
    user.profile_picture = f"/uploads/{path.name}"; db.commit()
    return {"profile_picture": user.profile_picture}

@app.post("/api/chat")
def chat(data: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    msg = data.message.lower()
    if "booking" in msg or "my ticket" in msg:
        bookings = db.query(Booking).filter(Booking.user_id == user.id).all()
        return {"reply": f"You have {len(bookings)} booking(s). Open My Bookings to see the details.", "suggestions": ["Trending events", "Recommended for you"]}
    if "trend" in msg or "popular" in msg:
        events = db.query(Event).filter(Event.is_active == True).all()
        events.sort(key=lambda e: e.tickets_sold + e.views, reverse=True)
        return {"reply": "Here are some trending events:", "events": [event_dict(e, db) for e in events[:5]]}
    if "recommend" in msg or "suggest" in msg or "music" in msg or "weekend" in msg or "near" in msg:
        events = db.query(Event).filter(Event.is_active == True).all()
        if "music" in msg: events = [e for e in events if "music" in e.category.lower() or "concert" in e.category.lower() or "music" in e.title.lower()]
        if "near" in msg and user.location: events = [e for e in events if user.location.lower() in e.location.lower()]
        events.sort(key=lambda e: e.tickets_sold + e.views, reverse=True)
        return {"reply": "I found these events that may match your request.", "events": [event_dict(e, db) for e in events[:5]]}
    return {"reply": "I can help find events, show trending events, check your booking count, and explain how to use SmartEvent. Try one of the suggestions below.", "suggestions": ["Trending events", "Recommend events", "Show my bookings"]}

@app.websocket("/ws/availability")
async def availability_ws(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws)

@app.post("/api/demo/seed")
def seed_demo(db: Session = Depends(get_db)):
    if db.query(Event).count(): return {"message": "Events already exist"}
    demos = [
        Event(title="Indie Music Night", description="Live independent music and local artists.", category="Music", location="Chennai", date="2026-11-14", price=499, total_tickets=120),
        Event(title="Startup & Tech Meetup", description="Networking and technology talks.", category="Technology", location="Chennai", date="2026-11-20", price=199, total_tickets=80),
        Event(title="Food Carnival", description="Street food, local chefs and family fun.", category="Food", location="Coimbatore", date="2026-11-28", price=99, total_tickets=200),
        Event(title="Stand-up Comedy Live", description="An evening of comedy and laughter.", category="Comedy", location="Chennai", date="2026-12-05", price=399, total_tickets=100),
    ]
    db.add_all(demos); db.commit()
    return {"message": "Demo events created", "count": len(demos)}
