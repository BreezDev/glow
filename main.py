from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Glow Atelier", description="Cosmetic booking experience")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

INJECTABLES = [
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

PRP = [
    {"name": "Vampire Facial (PRP)", "price": "$250/session", "duration": "60 min", "details": "Collagen-rich microneedling"},
    {"name": "PRP under eyes", "price": "$150/session", "duration": "45 min", "details": "Brighten + thicken skin"},
    {"name": "PRP hair restoration", "price": "$250/session", "duration": "60 min", "details": "Series-based protocol"},
    {"name": "PRP restoration plan", "price": "Treatment schedule", "duration": "Multi-visit", "details": "6-week cadence packages"},
]

PEELS = [
    {"name": "Perfect Derma Peel", "price": "$175", "duration": "45 min", "details": "Medium-depth resurfacing"},
    {"name": "Vampire Facial add-on", "price": "$250/session", "duration": "60 min", "details": "PRP-infused exfoliation"},
]

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "injectables": INJECTABLES,
            "prp": PRP,
            "peels": PEELS,
        },
    )
