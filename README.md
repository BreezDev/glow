# Glow Atelier FastAPI site

Modern FastAPI + Jinja front-end tailored for PythonAnywhere deployments. It
showcases Farah and Malak's cosmetic injectable, PRP, and peel offerings, and
walks clients through booking with Square, automated Resend emails, and consent
handling.

## Project structure
```
├── main.py              # FastAPI application + data definitions
├── templates/
│   └── index.html       # Luxe landing page fed by FastAPI context
├── static/
│   └── styles.css       # Gradient visual system + responsive layout
└── README.md            # Client/deployment playbook
```

## Local development
1. **Create and activate a virtualenv** (recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies**:
   ```bash
   pip install fastapi uvicorn jinja2
   ```
3. **Run the app**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
4. Visit `http://127.0.0.1:8000` to browse the immersive booking page. FastAPI
   hot-reloads template or CSS edits.

## PythonAnywhere deployment
1. Upload the repository (via Git clone or the file UI).
2. Create a **Virtualenv** inside PythonAnywhere with Python 3.10+ and install the
   same dependencies:
   ```bash
   pip install fastapi uvicorn jinja2
   ```
3. In the **Web** tab:
   - Set the **working directory** to this repo.
   - Point the **WSGI file** to load FastAPI using the standard snippet:
     ```python
     from fastapi import FastAPI
     from glow.main import app as application
     ```
     or, if the repo lives at `/home/USERNAME/glow`, update the Python path:
     ```python
     import sys
     path = '/home/USERNAME/glow'
     if path not in sys.path:
         sys.path.append(path)
     from main import app as application
     ```
   - Configure **Static files** mapping `/static/` → `/home/USERNAME/glow/static`.
4. Reload the site in PythonAnywhere. You should see the Glow Atelier landing page
   with all data-driven cards.

## Content editing
- **Services:** Update the `INJECTABLES`, `PRP`, or `PEELS` lists in `main.py`.
  Each item accepts `name`, `price`, `duration`, and `details`.
- **Copy + contact info:** Adjust hero text, bios, CTA links, and footer inside
  `templates/index.html`.
- **Visuals:** Modify gradients, typography, or layout tokens in `static/styles.css`.

## Square, Resend, and consent workflow
1. **Square**
   - Replace the placeholder booking link (`https://squareup.com/appointments`) in
     the “Book with Square” button with your actual Square Online Booking link.
   - Enable deposits + loyalty in Square Dashboard → Customers → Loyalty.
2. **Resend email automation**
   - Create templates for *Intake + prep*, *Appointment reminders*, and
     *Aftercare*. Each template should reference the same CTA link clients see on
     the website.
   - Trigger emails through your booking CRM (Square or a lightweight Zapier
     automation) that calls Resend's API when an appointment is created.
3. **Photo consent**
   - Keep a checkbox in your intake form (“I agree to photo/video capture”). If
     unchecked, skip before/after photos. The website copy already reassures
     clients that consent is optional.

## Quality checklist before launch
- [ ] Replace placeholder contact info and Instagram handle in the footer.
- [ ] Paste the live Square booking link and email address.
- [ ] Confirm the PythonAnywhere static mapping works (CSS + fonts load).
- [ ] Test on mobile (≤414px) to ensure cards, tabs, and hero layout remain
      polished.
- [ ] Send yourself a Resend test email to validate branding + content.
