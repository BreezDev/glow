import json
import os
import uuid
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, request
from urllib import error as urllib_error
from urllib import request as urllib_request


def build_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config["DEPOSIT_AMOUNT"] = int(os.getenv("DEPOSIT_AMOUNT", "150"))
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

    @app.post("/process-payment")
    def process_payment() -> Any:
        if not app.config["SQUARE_ACCESS_TOKEN"]:
            return jsonify({"error": "Square access token is not configured."}), 500

        payload: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
        token = payload.get("token")
        buyer_email = payload.get("email")
        guest_name = payload.get("name")
        amount = payload.get("amount")
        if not isinstance(amount, int):
            amount = app.config["DEPOSIT_AMOUNT"] * 100

        if not token:
            return jsonify({"error": "Payment token is required."}), 400

        headers = {
            "Authorization": f"Bearer {app.config['SQUARE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Square-Version": "2024-06-12",
        }
        body = {
            "idempotency_key": str(uuid.uuid4()),
            "amount_money": {"amount": amount, "currency": "USD"},
            "source_id": token,
            "location_id": app.config["SQUARE_LOCATION_ID"],
            "autocomplete": True,
            "note": "Glow Atelier reservation deposit",
        }
        if buyer_email:
            body["buyer_email_address"] = buyer_email
        if guest_name:
            body["billing_address"] = {"first_name": guest_name.split(" ")[0]}

        payload_bytes = json.dumps(body).encode("utf-8")
        request_obj = urllib_request.Request(
            url=f"{app.config['SQUARE_API_BASE']}/v2/payments",
            data=payload_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib_request.urlopen(request_obj, timeout=10) as response:
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
