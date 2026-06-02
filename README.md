# RideDelivery API

A FastAPI-based ride-hailing and delivery platform for the Kenyan market (M-Pesa, KSH pricing).

## Stack

- **FastAPI** — async API framework
- **SQLAlchemy 2 (async)** — ORM with PostgreSQL
- **Celery + Redis** — background job queues (rider assignment, notifications, payments)
- **M-Pesa Daraja** — STK Push payments
- **JWT** — stateless auth

---

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate   

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp src/env.example .env
# Edit .env with your DB, Redis, M-Pesa credentials

# 4. Run migrations
alembic upgrade head

# 5. Start API server
uvicorn src.main:app --reload

# 6. Start Celery workers (separate terminals)
celery -A src.jobs.celery_app worker -Q rides -c 4 --loglevel=info
celery -A src.jobs.celery_app worker -Q notifications -c 4 --loglevel=info
celery -A src.jobs.celery_app worker -Q payments -c 2 --loglevel=info

# 7. for windows -->
celery -A src.jobs.celery_app worker -Q rides -P solo -n rides@%h --loglevel=info
celery -A src.jobs.celery_app worker -Q notifications -P solo -n notifications@%h --loglevel=info
celery -A src.jobs.celery_app worker -Q payments -P solo -n payments@%h --loglevel=info
```


---

## API Routes

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register customer/rider |
| POST | `/api/v1/auth/login` | Login → JWT token |

### Customer
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/customer/fare-estimate` | Get fare before booking |
| POST | `/api/v1/customer/requests` | Create ride/delivery request |
| GET | `/api/v1/customer/requests` | My request history |
| POST | `/api/v1/customer/requests/{id}/cancel` | Cancel a request |
| GET | `/api/v1/customer/billing/{request_id}` | View bill |
| POST | `/api/v1/customer/payments/initiate` | Pay via M-Pesa STK Push |
| POST | `/api/v1/customer/ratings` | Rate a rider |
| POST | `/api/v1/customer/favourites/{rider_id}` | Save favourite rider |
| GET | `/api/v1/customer/notifications` | My notifications |

### Rider
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rider/availability` | Go online/offline + update location |
| POST | `/api/v1/rider/location` | Heartbeat location update |
| GET | `/api/v1/rider/assignments/pending` | View pending job requests |
| POST | `/api/v1/rider/assignments/{id}/respond` | Accept or reject a job |
| GET | `/api/v1/rider/trips/active` | Active trips |
| POST | `/api/v1/rider/trips/{id}/start` | Mark trip started |
| POST | `/api/v1/rider/trips/{id}/complete` | Mark trip completed |
| POST | `/api/v1/rider/ratings` | Rate a customer |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/v1/admin/pricing` | View/update pricing per km |
| POST | `/api/v1/admin/assign-rider` | Manually assign any rider to any job |
| GET | `/api/v1/admin/escalated-requests` | Jobs no rider accepted |
| GET | `/api/v1/admin/users` | List all users |
| POST | `/api/v1/admin/users/{id}/deactivate` | Deactivate a user |
| GET | `/api/v1/admin/stats` | Dashboard totals |

### Payments (Webhook)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/payments/mpesa/callback` | Safaricom STK Push result |

---

## Rider Assignment Flow

```
Customer creates request
        │
        ▼
[Celery] dispatch_ride_search
        │
        ├─► Find nearest available rider within radius
        │         (radius expands with each attempt)
        │
        ├─► Create RequestAssignment (status=pending)
        │
        ├─► Notify rider via Notification table
        │
        └─► Schedule assignment_timeout_task (5 min)
                  │
         ┌────────┴────────┐
     Rider responds     No response
         │                 │
    accept/reject     timeout_task fires
         │                 │
    revoke timeout    mark timeout → retry
         │
      accepted → Request.status = assigned
      rejected → dispatch_ride_search (next rider)

After MAX_ATTEMPTS → escalate_to_admin
```

---

## Favourite Rider Notifications

When a rider calls `POST /rider/availability` with `is_available: true`,
the system fires a Celery task that notifies every customer who has that rider
saved as a favourite — no polling required.

---

## Improvements Roadmap

See the suggestions in the codebase comments. Key items:

1. **WebSockets** — real-time location tracking for customers watching their rider
2. **Firebase FCM** — push notifications to mobile apps (replace DB-only notifications)
3. **Africa's Talking SMS** — SMS fallback when rider has no internet
4. **Surge pricing** — auto-adjust `surge_multiplier` based on demand/supply ratio
5. **OTP phone verification** — verify phone numbers on registration
6. **Driver documents** — store national ID, license scans, approval workflow
7. **Wallet top-up** — riders can withdraw earnings via M-Pesa B2C
8. **Rate limiting** — per-user API rate limits via Redis
9. **Prometheus metrics** — expose `/metrics` for Grafana dashboards
10. **Docker Compose** — containerize API + workers + Redis + Postgres
