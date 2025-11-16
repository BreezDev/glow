import json
import os
import time
import uuid
import pytz
from collections import deque
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request
from urllib import error as urllib_error
from urllib import request as urllib_request

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Correct timezone (handles EST & EDT automatically)
NY = pytz.timezone("America/New_York")

# Load free coupon codes (comma-separated)
free_codes = os.getenv("FREE_COUPON_CODES", "")
free_codes = [c.strip().upper() for c in free_codes.split(",") if c.strip()]


class BurstRateLimiter:
    """Very small, in-memory rate limiter to keep Resend under 2 RPS."""

    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self.events: deque[float] = deque()

    def consume(self) -> None:
        now = time.time()
        while self.events and now - self.events[0] > self.per_seconds:
            self.events.popleft()

        if len(self.events) >= self.max_calls:
            sleep_for = self.per_seconds - (now - self.events[0])
            time.sleep(max(0, sleep_for))
        self.events.append(time.time())


def build_offline_availability(days: int = 14) -> Dict[str, List[str]]:
    schedule_env = os.getenv("GLOW_AVAILABILITY_JSON")
    if schedule_env:
        try:
            loaded = json.loads(schedule_env)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

    today = date.today()
    start_time = time(9, 0)
    end_time = time(19, 0)
    slot_length = timedelta(minutes=45)

    availability: Dict[str, List[str]] = {}

    for offset in range(days):
        day = today + timedelta(days=offset)
        slots = []

        current_dt = datetime.combine(day, start_time)
        end_dt = datetime.combine(day, end_time)

        while current_dt <= end_dt:
            est_dt = NY.localize(current_dt)
            slots.append(est_dt.strftime("%I:%M %p"))
            current_dt += slot_length

        availability[day.isoformat()] = slots

    return availability


def call_square_api(
    base: str, path: str, *, token: str, method: str = "GET", body: Optional[dict] = None
) -> Tuple[int, dict]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Square-Version": "2024-06-12",
    }
    data_bytes = json.dumps(body).encode("utf-8") if body is not None else None

    req = urllib_request.Request(
        url=f"{base}{path}",
        data=data_bytes,
        headers=headers,
        method=method,
    )

    with urllib_request.urlopen(req, timeout=12) as res:
        payload = res.read()
        parsed = json.loads(payload) if payload else {}
        return res.status, parsed


def fetch_square_availability(
    *,
    base: str,
    token: str,
    location_id: str,
    days: int = 14,
) -> Optional[Dict[str, List[str]]]:
    """Pull live availability from Square's Booking availability search API."""

    start_at = datetime.utcnow()
    end_at = start_at + timedelta(days=days)

    query = {
        "query": {
            "filter": {
                "location_id": location_id,
                "start_at_range": {
                    "start_at": start_at.isoformat() + "Z",
                    "end_at": end_at.isoformat() + "Z",
                },
            }
        }
    }

    try:
        status, payload = call_square_api(
            base,
            "/v2/bookings/availability/search",
            token=token,
            method="POST",
            body=query,
        )
    except Exception:
        return None

    if status >= 400:
        return None

    slots: Dict[str, List[str]] = {}
    for slot in payload.get("availabilities", []):
        start_at_str: str = slot.get("start_at", "")
        try:
            start_dt = datetime.fromisoformat(start_at_str.replace("Z", "+00:00")).astimezone(NY)
        except ValueError:
            continue
        day_key = start_dt.date().isoformat()
        slots.setdefault(day_key, []).append(start_dt.strftime("%I:%M %p"))

    return slots or None


def build_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Config
    app.config["DEPOSIT_AMOUNT"] = 50  # ALWAYS $50
    app.config["SQUARE_APPLICATION_ID"] = os.getenv("SQUARE_APPLICATION_ID", "")
    app.config["SQUARE_LOCATION_ID"] = os.getenv("SQUARE_LOCATION_ID", "")
    app.config["SQUARE_ACCESS_TOKEN"] = os.getenv("SQUARE_ACCESS_TOKEN")

    environment = os.getenv("SQUARE_ENVIRONMENT", "sandbox").lower()
    if environment not in {"production", "sandbox"}:
        environment = "sandbox"
    app.config["SQUARE_ENVIRONMENT"] = environment

    if environment == "production":
        app.config["SQUARE_API_BASE"] = "https://connect.squareup.com"
        app.config["SQUARE_JS_SRC"] = "https://web.squarecdn.com/v1/square.js"
    else:
        app.config["SQUARE_API_BASE"] = "https://connect.squareupsandbox.com"
        app.config["SQUARE_JS_SRC"] = "https://sandbox.web.squarecdn.com/v1/square.js"

    # Services
    injectables = [
        {"name": "Botox smooth", "price": "$9/unit", "duration": "15 min", "details": "Quick wrinkle softening"},
        {"name": "Botox refresh", "price": "$9/unit", "duration": "30 min", "details": "Balanced upper-face map"},
        {"name": "Botox touch up", "price": "Complimentary", "duration": "10 min", "details": "2-week tweak"},
        {"name": "Lip filler", "price": "$400", "duration": "45 min", "details": "Soft, even volume"},
        {"name": "Lip flip", "price": "$60+", "duration": "15 min", "details": "Defined border"},
        {"name": "Cheek filler", "price": "$400+", "duration": "45 min", "details": "Lifted midface"},
        {"name": "Jaw filler", "price": "$400+", "duration": "60 min", "details": "Sharper line"},
        {"name": "Nose filler", "price": "$400+", "duration": "30 min", "details": "Smoother bridge"},
        {"name": "Nasolabial folds", "price": "$400+", "duration": "45 min", "details": "Softened smile lines"},
        {"name": "Temple filler", "price": "$400", "duration": "30 min", "details": "Temple support"},
        {"name": "SkinVive", "price": "Custom", "duration": "30 min", "details": "Skin hydration"},
        {"name": "Kybella", "price": "Consult", "duration": "60 min", "details": "Chin contour"},
        {"name": "Sculptra", "price": "$550+", "duration": "60 min", "details": "Collagen boost"},
    ]

    prp = [
        {"name": "PRP facial", "price": "$250/session", "duration": "60 min", "details": "Microneedling + PRP"},
        {"name": "PRP under eyes", "price": "$150/session", "duration": "45 min", "details": "Brighten + thicken"},
        {"name": "PRP hair restoration", "price": "$250/session", "duration": "60 min", "details": "Scalp stimulation"},
    ]

    peels = [
        {"name": "Perfect Derma Peel", "price": "$175", "duration": "45 min", "details": "Refined glow"},
        {"name": "Glow peel add-on", "price": "$125", "duration": "30 min", "details": "Fast exfoliation"},
    ]

    resend_limiter = BurstRateLimiter(2, 1.0)

    def get_availability(days: int = 30) -> Tuple[Dict[str, List[str]], str]:
        token = app.config["SQUARE_ACCESS_TOKEN"]
        location_id = app.config["SQUARE_LOCATION_ID"]
        base = app.config["SQUARE_API_BASE"]

        if token and location_id:
            live_slots = fetch_square_availability(
                base=base, token=token, location_id=location_id, days=days
            )
            if live_slots:
                return live_slots, "square"

        return build_offline_availability(days), "offline"

    availability_cache: Dict[str, Any] = {"slots": {}, "source": "offline", "ts": 0.0}

    # Landing Page
    @app.get("/")
    def landing():
        if time.time() - availability_cache["ts"] > 60 or not availability_cache["slots"]:
            slots, source = get_availability(30)
            availability_cache.update({"slots": slots, "source": source, "ts": time.time()})
        return render_template(
            "index.html",
            injectables=injectables,
            prp=prp,
            peels=peels,
            availability=availability_cache["slots"],
            square_application_id=app.config["SQUARE_APPLICATION_ID"],
            square_location_id=app.config["SQUARE_LOCATION_ID"],
            square_js_src=app.config["SQUARE_JS_SRC"],
            deposit_amount=50,  # always $50
        )

    # Email Sending
    def send_resend_confirmation(
        *,
        guest_email: str,
        guest_name: str,
        appointment_date: str,
        appointment_time: str,
        cart_items: List[Dict[str, Any]],
        deposit_total: float,
    ) -> None:
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            return

        resend_limiter.consume()

        recipients = ["farah@glowmedi.clinic", "malak@glowmedi.clinic"]
        if guest_email:
            recipients.insert(0, guest_email)

        line_items = "".join(
            f"<li>{item.get('name')} — Qty {item.get('quantity', 1)}</li>"
            for item in cart_items
        )

        html_body = f"""
            <p>Hi {guest_name or 'Glow guest'},</p>
            <p>Your reservation has been confirmed.</p>
            <ul>
              <li><strong>Date</strong>: {appointment_date}</li>
              <li><strong>Time</strong>: {appointment_time}</li>
              <li><strong>Deposit</strong>: ${deposit_total:.2f}</li>
            </ul>
            <p><strong>Selected rituals:</strong></p>
            <ul>{line_items}</ul>
        """

        body = json.dumps(
            {
                "from": "GlowMedi <bookings@glowmedi.clinic>",
                "to": recipients,
                "subject": "GlowMedi reservation confirmation",
                "html": html_body,
            }
        ).encode("utf-8")

        req = urllib_request.Request(
            url="https://api.resend.com/emails",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )

        try:
            urllib_request.urlopen(req, timeout=10)
        except urllib_error.URLError:
            pass

    def ensure_square_customer(*, name: str, email: str, phone: str) -> Optional[str]:
        token = app.config["SQUARE_ACCESS_TOKEN"]
        base = app.config["SQUARE_API_BASE"]
        if not token:
            return None

        body = {
            "idempotency_key": str(uuid.uuid4()),
            "given_name": name or "Glow Guest",
            "email_address": email,
            "phone_number": phone,
        }

        try:
            _, payload = call_square_api(
                base,
                "/v2/customers",
                token=token,
                method="POST",
                body=body,
            )
            return payload.get("customer", {}).get("id")
        except Exception:
            return None

    def create_square_booking(
        *,
        customer_id: Optional[str],
        appointment_date: str,
        appointment_time: str,
        note: str,
        cart_items: List[Dict[str, Any]],
    ) -> Optional[str]:
        token = app.config["SQUARE_ACCESS_TOKEN"]
        location_id = app.config["SQUARE_LOCATION_ID"]
        base = app.config["SQUARE_API_BASE"]
        if not token or not location_id:
            return None

        try:
            start_dt = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %I:%M %p")
            start_utc = NY.localize(start_dt).astimezone(pytz.utc)
        except Exception:
            return None

        body = {
            "idempotency_key": str(uuid.uuid4()),
            "location_id": location_id,
            "customer_id": customer_id,
            "start_at": start_utc.isoformat().replace("+00:00", "Z"),
            "appointment_segments": [
                {
                    "duration_minutes": 45,
                    "service_variation_id": cart_items[0].get("name", "Service"),
                    "team_member_id": None,
                }
            ],
            "customer_note": note,
        }

        try:
            _, payload = call_square_api(
                base,
                "/v2/bookings",
                token=token,
                method="POST",
                body=body,
            )
            return payload.get("booking", {}).get("id")
        except Exception:
            return None

    def enroll_loyalty_account(*, customer_id: str, phone: str) -> Optional[str]:
        token = app.config["SQUARE_ACCESS_TOKEN"]
        base = app.config["SQUARE_API_BASE"]
        if not token:
            return None

        body = {
            "idempotency_key": str(uuid.uuid4()),
            "loyalty_account": {
                "program_id": os.getenv("SQUARE_LOYALTY_PROGRAM_ID", ""),
                "mapping": {"phone_number": phone},
                "customer_id": customer_id,
            },
        }

        try:
            _, payload = call_square_api(
                base,
                "/v2/loyalty/accounts",
                token=token,
                method="POST",
                body=body,
            )
            return payload.get("loyalty_account", {}).get("id")
        except Exception:
            return None

    # PAYMENT PROCESSING
    @app.post("/process-payment")
    def process_payment():
        payload = request.get_json(force=True, silent=True) or {}

        token = payload.get("token")
        coupon = (payload.get("coupon") or "").upper()
        buyer_email = payload.get("email")
        guest_name = payload.get("name")
        phone = payload.get("phone")
        appointment_date = payload.get("appointmentDate")
        appointment_time = payload.get("appointmentTime")
        cart_items = payload.get("cart", [])
        customer_id = payload.get("customerId")
        note = payload.get("note") or "Website booking"

        if not cart_items:
            return jsonify({"error": "Cart is empty."}), 400

        is_free = coupon in free_codes
        deposit_amount = 0 if is_free else 50
        amount_cents = deposit_amount * 100

        # Ensure customer exists before booking / payment
        if not customer_id:
            customer_id = ensure_square_customer(name=guest_name or "Guest", email=buyer_email or "", phone=phone or "")

        # --- IF FREE: skip Square entirely ---
        if is_free:
            booking_id = create_square_booking(
                customer_id=customer_id,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                note=note,
                cart_items=cart_items,
            )
            send_resend_confirmation(
                guest_email=buyer_email or "",
                guest_name=guest_name or "",
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                cart_items=cart_items,
                deposit_total=0.00,
            )
            return jsonify({"status": "success", "paymentId": None, "bookingId": booking_id})

        # ---- Normal Square Payment ----
        if not token:
            return jsonify({"error": "Payment token is required."}), 400

        headers = {
            "Authorization": f"Bearer {app.config['SQUARE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Square-Version": "2024-06-12",
        }

        # Create order
        order_body = {
            "idempotency_key": str(uuid.uuid4()),
            "order": {
                "location_id": app.config["SQUARE_LOCATION_ID"],
                "line_items": [
                    {
                        "name": item.get("name", "Glow service"),
                        "quantity": str(item.get("quantity", 1)),
                        "base_price_money": {
                            "amount": 5000,  # DEPOSIT ONLY, not full service charge
                            "currency": "USD",
                        },
                    }
                    for item in cart_items
                ],
                "note": f"Requested {appointment_date} at {appointment_time} | Phone: {phone or 'N/A'}",
            },
        }

        order_req = urllib_request.Request(
            url=f"{app.config['SQUARE_API_BASE']}/v2/orders",
            data=json.dumps(order_body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(order_req, timeout=10) as res:
                order_data = json.loads(res.read())
        except:
            return jsonify({"error": "Unable to create order."}), 500

        order_id = order_data.get("order", {}).get("id")

        # Payment
        payment_body = {
            "idempotency_key": str(uuid.uuid4()),
            "amount_money": {"amount": amount_cents, "currency": "USD"},
            "source_id": token,
            "location_id": app.config["SQUARE_LOCATION_ID"],
            "autocomplete": True,
            "order_id": order_id,
        }

        pay_req = urllib_request.Request(
            url=f"{app.config['SQUARE_API_BASE']}/v2/payments",
            data=json.dumps(payment_body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(pay_req, timeout=10) as res:
                pay_data = json.loads(res.read())
        except urllib_error.HTTPError as exc:
            return jsonify({"error": exc.read().decode()}), exc.code

        booking_id = create_square_booking(
            customer_id=customer_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            note=note,
            cart_items=cart_items,
        )

        # Send confirmation
        send_resend_confirmation(
            guest_email=buyer_email or "",
            guest_name=guest_name or "",
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            cart_items=cart_items,
            deposit_total=float(deposit_amount),
        )

        return jsonify(
            {
                "status": "success",
                "paymentId": pay_data.get("payment", {}).get("id"),
                "bookingId": booking_id,
            }
        )

    # Availability Feed
    @app.get("/availability")
    def availability_feed():
        now = time.time()
        if now - availability_cache["ts"] > 60:
            slots, source = get_availability(30)
            availability_cache.update({"slots": slots, "source": source, "ts": now})
        return jsonify({"availability": availability_cache["slots"], "source": availability_cache["source"]})

    @app.post("/accounts")
    def create_account():
        payload = request.get_json(force=True, silent=True) or {}
        name = payload.get("name")
        email = payload.get("email")
        phone = payload.get("phone")
        notes = payload.get("notes")

        customer_id = ensure_square_customer(name=name or "Guest", email=email or "", phone=phone or "")
        loyalty_id = None
        if customer_id and phone:
            loyalty_id = enroll_loyalty_account(customer_id=customer_id, phone=phone)

        return jsonify({"customerId": customer_id, "loyaltyId": loyalty_id, "notes": notes})

    @app.post("/loyalty")
    def join_loyalty():
        payload = request.get_json(force=True, silent=True) or {}
        customer_id = payload.get("customerId")
        phone = payload.get("phone")
        if not (customer_id and phone):
            return jsonify({"error": "Customer and phone required"}), 400
        loyalty_id = enroll_loyalty_account(customer_id=customer_id, phone=phone)
        if not loyalty_id:
            return jsonify({"error": "Unable to enroll"}), 500
        return jsonify({"loyaltyId": loyalty_id})

    return app


app = build_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
