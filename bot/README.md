# 🛍 Telegram Selling Bot

Production-ready Telegram bot for selling digital products with UPI payment support.

## Tech Stack

- **Python 3.11+**
- **Aiogram 3.x** — async Telegram bot framework
- **SQLAlchemy 2.0** — async ORM
- **SQLite** (dev) / **PostgreSQL** (prod)
- **APScheduler** — order auto-expiry
- **qrcode + Pillow** — UPI QR generation

---

## Project Structure

```
bot/
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
│
├── config/
│   └── settings.py            # All config via .env
│
├── database/
│   ├── connection.py          # Engine, session factory, seeding
│   └── models.py              # SQLAlchemy ORM models
│
├── services/
│   └── db_service.py          # All database operations (CRUD)
│
├── handlers/
│   ├── user/
│   │   ├── start.py           # /start, main menu
│   │   ├── products.py        # Browse, paginate, plan selection
│   │   ├── payment.py         # Order creation, QR, screenshot
│   │   └── orders.py          # My orders history
│   └── admin/
│       ├── panel.py           # /admin command, stats
│       ├── products.py        # Add/edit/delete products & plans
│       ├── payments.py        # Approve/reject payments
│       ├── orders.py          # Deliver orders
│       ├── admins.py          # Manage admin users
│       ├── settings.py        # UPI, timeout, welcome msg
│       └── broadcast.py       # Message all users
│
├── middlewares/
│   ├── auth.py                # Auto user upsert + inject admin role
│   ├── throttle.py            # Per-user rate limiting
│   └── role_filter.py         # RBAC filters for handlers
│
├── keyboards/
│   └── keyboards.py           # All inline keyboard builders
│
├── states/
│   └── states.py              # All FSM state groups
│
├── scheduler/
│   └── expiry.py              # Auto-expire pending orders
│
└── utils/
    ├── order_id.py            # Unique order ID generator
    └── qr_generator.py        # UPI QR code (PNG bytes)
```

---

## Setup

### 1. Clone and install

```bash
git clone <repo>
cd bot
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set BOT_TOKEN, OWNER_ID, UPI_ID
```

**Get your Telegram user ID:**  
Message [@userinfobot](https://t.me/userinfobot) on Telegram.

### 3. Run

```bash
python main.py
```

On first run, the database is created automatically and your OWNER_ID is seeded as admin.

---

## Usage

### User Flow

1. `/start` → Main Menu
2. **Products** → Browse with pagination (5/page)
3. Select product → View details
4. Select plan → Order summary
5. **Confirm** → UPI QR code + payment instructions
6. **"I've sent payment"** → Upload screenshot
7. Wait for admin approval → Receive product

### Admin Commands

| Command | Access |
|---------|--------|
| `/admin` | All admins |

### Admin Panel Sections

| Section | Role Required |
|---------|---------------|
| 📦 Products | product_admin + |
| 💳 Payments | payment_admin + |
| 📬 Orders | order_admin + |
| 👥 Admins | super_admin + |
| ⚙️ Settings | super_admin + |
| 📊 Stats | All admins |
| 📢 Broadcast | super_admin + |

---

## Roles

| Role | Permissions |
|------|------------|
| `owner` | Full access |
| `super_admin` | Everything except owner ops |
| `product_admin` | Manage products/plans |
| `payment_admin` | Approve/reject payments |
| `order_admin` | Deliver orders |

---

## Production Deployment

### Switch to PostgreSQL

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/shopbot
```

### Webhook (instead of polling)

```python
# In main.py, replace dp.start_polling with:
await bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
```

### Process Manager

```bash
pip install supervisor
# or use systemd / Docker
```

### Database Migrations (Alembic)

When you make changes to your database models (`database/models.py`), you need to create and apply migrations:

```bash
# Generate a new migration script
alembic revision --autogenerate -m "Describe your changes"

# Apply migrations to the database
alembic upgrade head
```

---

## Order Status Flow

```
pending → submitted → paid → delivered
    ↓          ↓
  expired    rejected
```

- **pending**: Created, waiting for screenshot (10 min timeout)
- **submitted**: Screenshot received, awaiting admin review
- **paid**: Payment approved by admin
- **delivered**: Product sent to user
- **expired**: No screenshot within timeout
- **rejected**: Admin rejected the payment
