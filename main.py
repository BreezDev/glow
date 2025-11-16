import json
import os
import uuid
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request
from urllib import error as urllib_error
from urllib import request as urllib_request


def build_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config["DEPOSIT_AMOUNT"] = int(os.getenv("DEPOSIT_AMOUNT", "50"))
    app.config["SQUARE_APPLICATION_ID"] = os.getenv("SQUARE_APPLICATION_ID", "sq0idp-placeholder")
    app.config["SQUARE_LOCATION_ID"] = os.getenv("SQUARE_LOCATION_ID", "L88917HQXXXX")
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

    injectables: List[Dict[str, str]] = [
        {"name": "Botox with Farah", "price": "$9/unit", "duration": "15 min", "details": "Precise wrinkle relaxation"},
        {"name": "Botox with Malak", "price": "$9/unit", "duration": "30 min", "details": "Express appointment"},
        {"name": "Botox touch up", "price": "Complimentary", "duration": "10 min", "details": "2-week follow up with Farah or Malak"},
        {"name": "Lip filler", "price": "$400", "duration": "45 min", "details": "Full, balanced volume"},
        {"name": "Lip filler touch up", "price": "Existing clients", "duration": "10 min", "details": "Maintenance visit"},
        {"name": "Lip Flip", "price": "$60+", "duration": "15 min", "details": "Botox lip definition"},
        {"name": "Cheek filler", "price": "$400+", "duration": "45 min", "details": "Midface contour"},
        {"name": "Jaw filler", "price": "$400+", "duration": "60 min", "details": "Snatched jawline"},
        {"name": "Nose filler", "price": "$400+", "duration": "30 min", "details": "Non-surgical contour"},
        {"name": "Nasolabial folds", "price": "$400+", "duration": "45 min", "details": "Laugh line softening"},
        {"name": "Temple filler", "price": "$400", "duration": "30 min", "details": "Temple balance"},
        {"name": "SkinVive", "price": "Custom", "duration": "30 min", "details": "Juvederm glow"},
        {"name": "Kybella", "price": "Consult", "duration": "60 min", "details": "Targeted fat reduction"},
        {"name": "Sculptra", "price": "$550+", "duration": "60 min", "details": "Collagen biostimulator"},
        {"name": "Kenalog injections", "price": "Consult", "duration": "15 min", "details": "Inflammation control"},
    ]

    prp: List[Dict[str, str]] = [
        {"name": "Vampire Facial (PRP)", "price": "$250/session", "duration": "60 min", "details": "Collagen-rich microneedling"},
        {"name": "PRP under eyes", "price": "$150/session", "duration": "45 min", "details": "Brighten + thicken skin"},
        {"name": "PRP hair restoration", "price": "$250/session", "duration": "60 min", "details": "Series-based protocol"},
        {"name": "PRP restoration plan", "price": "Treatment schedule", "duration": "Multi-visit", "details": "6-week cadence packages"},
    ]

    peels: List[Dict[str, str]] = [
        {"name": "Perfect Derma Peel", "price": "$175", "duration": "45 min", "details": "Medium-depth resurfacing"},
        {"name": "Vampire Facial add-on", "price": "$250/session", "duration": "60 min", "details": "PRP-infused exfoliation"},
    ]

    @app.get("/")
    def landing() -> str:
        return render_template(
            "index.html",
            injectables=injectables,
            prp=prp,
            peels=peels,
            square_application_id=app.config["SQUARE_APPLICATION_ID"],
            square_location_id=app.config["SQUARE_LOCATION_ID"],
            square_js_src=app.config["SQUARE_JS_SRC"],
            deposit_amount=app.config["DEPOSIT_AMOUNT"],
        )

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
        if not api_key or not guest_email:
            return

        subject = "Glow Atelier reservation confirmation"
        line_items = "".join(
            f"<li>{item.get('name')} — Qty {item.get('quantity', 1)}</li>" for item in cart_items
        )
        html_body = f"""
            <p>Hi {guest_name or 'Glow guest'},</p>
            <p>Thank you for reserving with Glow Atelier. We've captured your deposit and confirmed your requested slot.</p>
            <ul>
              <li><strong>Date</strong>: {appointment_date}</li>
              <li><strong>Time</strong>: {appointment_time}</li>
              <li><strong>Deposit</strong>: ${deposit_total:.2f}</li>
            </ul>
            <p><strong>Selected rituals</strong>:</p>
            <ul>{line_items}</ul>
            <p>We'll reach out shortly to finalize any details.</p>
        """

        body = json.dumps(
            {
                "from": "Glow Atelier <bookings@glowatelier.com>",
                "to": [guest_email, "farah@glowmedi.clinic", "malak@glowmedi.clinic"],
                "subject": subject,
                "html": html_body,
            }
        ).encode("utf-8")

        request_obj = urllib_request.Request(
            url="https://api.resend.com/emails",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            urllib_request.urlopen(request_obj, timeout=10)
        except urllib_error.URLError:
            return

    @app.post("/process-payment")
    def process_payment() -> Any:
        if not app.config["SQUARE_ACCESS_TOKEN"]:
            return jsonify({"error": "Square access token is not configured."}), 500

        payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
        token = payload.get("token")
        buyer_email = payload.get("email")
        guest_name = payload.get("name")
        phone = payload.get("phone")
        appointment_date = payload.get("appointmentDate")
        appointment_time = payload.get("appointmentTime")
        cart_items = payload.get("cart", [])

        if not token:
            return jsonify({"error": "Payment token is required."}), 400
        if not cart_items:
            return jsonify({"error": "Cart is empty. Please add a treatment before checkout."}), 400
        if not appointment_date or not appointment_time:
            return jsonify({"error": "Appointment date and time are required."}), 400

        deposit_amount = app.config["DEPOSIT_AMOUNT"] * max(sum(int(item.get("quantity", 1)) for item in cart_items), 1)
        amount_cents = deposit_amount * 100

        headers = {
            "Authorization": f"Bearer {app.config['SQUARE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Square-Version": "2024-06-12",
        }

        order_details: Dict[str, Any] = {
            "location_id": app.config["SQUARE_LOCATION_ID"],
            "line_items": [
                {
                    "name": item.get("name", "Glow service"),
                    "quantity": str(item.get("quantity", 1)),
                    "base_price_money": {
                        "amount": app.config["DEPOSIT_AMOUNT"] * 100,
                        "currency": "USD",
                    },
                }
                for item in cart_items
            ],
            "note": f"Requested {appointment_date} at {appointment_time} | Phone: {phone or 'N/A'}",
        }

        if guest_name:
            order_details["reference_id"] = f"Booking for {guest_name}"

        order_body = {
            "idempotency_key": str(uuid.uuid4()),
            "order": order_details,
        }

        order_bytes = json.dumps(order_body).encode("utf-8")
        order_request = urllib_request.Request(
            url=f"{app.config['SQUARE_API_BASE']}/v2/orders",
            data=order_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(order_request, timeout=10) as response:
                order_status = response.getcode()
                order_response = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            order_status = exc.code
            order_response = exc.read().decode("utf-8")
        except urllib_error.URLError as exc:  # pragma: no cover - network failure
            return jsonify({"error": f"Unable to reach Square: {exc.reason}"}), 502

        order_data = json.loads(order_response or "{}")
        if not (200 <= order_status < 300):
            errors = order_data.get("errors")
            message = errors[0].get("detail") if errors else "Unable to create order."
            return jsonify({"error": message}), order_status

        order_id = order_data.get("order", {}).get("id")

        payment_body = {
            "idempotency_key": str(uuid.uuid4()),
            "amount_money": {"amount": amount_cents, "currency": "USD"},
            "source_id": token,
            "location_id": app.config["SQUARE_LOCATION_ID"],
            "autocomplete": True,
            "note": "Glow Atelier reservation deposit",
            "order_id": order_id,
        }
        if buyer_email:
            payment_body["buyer_email_address"] = buyer_email
        if guest_name:
            payment_body["billing_address"] = {"first_name": guest_name.split(" ")[0]}

        payment_bytes = json.dumps(payment_body).encode("utf-8")
        payment_request = urllib_request.Request(
            url=f"{app.config['SQUARE_API_BASE']}/v2/payments",
            data=payment_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(payment_request, timeout=10) as response:
                status_code = response.getcode()
                response_body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            status_code = exc.code
            response_body = exc.read().decode("utf-8")
        except urllib_error.URLError as exc:  # pragma: no cover - network failure
            return jsonify({"error": f"Unable to reach Square: {exc.reason}"}), 502

        data = json.loads(response_body or "{}")
        if 200 <= status_code < 300:
            payment = data.get("payment", {})
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
                    "status": payment.get("status", "SUCCESS"),
                    "paymentId": payment.get("id"),
                    "receiptUrl": payment.get("receipt_url"),
                }
            )

        errors = data.get("errors")
        message = errors[0].get("detail") if errors else "Payment failed."
        return jsonify({"error": message}), status_code

    return app


app = build_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
