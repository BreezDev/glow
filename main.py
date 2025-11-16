import json
import os
import uuid
import pytz
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List

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


def build_availability(days: int = 7) -> Dict[str, List[str]]:
    schedule_env = os.getenv("GLOW_AVAILABILITY_JSON")
    if schedule_env:
        try:
            loaded = json.loads(schedule_env)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

    today = date.today()
    start_time = time(10, 0)
    end_time = time(18, 0)
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

    availability = build_availability()

    # Landing Page
    @app.get("/")
    def landing():
        return render_template(
            "index.html",
            injectables=injectables,
            prp=prp,
            peels=peels,
            availability=availability,
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

        if not cart_items:
            return jsonify({"error": "Cart is empty."}), 400

        is_free = coupon in free_codes
        deposit_amount = 0 if is_free else 50
        amount_cents = deposit_amount * 100

        # --- IF FREE: skip Square entirely ---
        if is_free:
            send_resend_confirmation(
                guest_email=buyer_email or "",
                guest_name=guest_name or "",
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                cart_items=cart_items,
                deposit_total=0.00,
            )
            return jsonify({"status": "success", "paymentId": None})

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

        # Send confirmation
        send_resend_confirmation(
            guest_email=buyer_email or "",
            guest_name=guest_name or "",
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            cart_items=cart_items,
            deposit_total=float(deposit_amount),
        )

        return jsonify({"status": "success", "paymentId": pay_data.get("payment", {}).get("id")})

    # Availability Feed
    @app.get("/availability")
    def availability_feed():
        return jsonify({"availability": availability})

    return app


app = build_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
