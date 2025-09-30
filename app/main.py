from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from config.db import get_db, init_db, SessionLocal
from config.constants import CURRENCY_SYMBOLS
from models import Account, Invoice, User
from auth import get_current_user, require_admin, hash_password
from routes.accounts import router as accounts_router
from routes.health import router as health_router
from routes.transactions import router as transactions_router
from routes.frequents import router as frequents_router
from routes.exportables import router as exportables_router
from routes.invoices import router as invoices_router
from routes.users import router as users_router
from routes.billing_info import router as billing_info_router
from routes.billing_movements import router as billing_movements_router
from routes.notifications import router as notifications_router
from routes.inkwell import router as inkwell_router
from services.notifications import start_notification_retention_job, stop_notification_retention_job

load_dotenv()


app = FastAPI(title="Movimientos")


@app.middleware("http")
async def require_login_middleware(request: Request, call_next):
    path = request.url.path
    if (
        path == "/notificaciones"
        and request.method.upper() == "POST"
        and request.headers.get("X-Signature")
    ):
        return await call_next(request)

    allowed = {
        "/login",
        "/register",
        "/health",
        "/facturacion-info",
        "/movimientos_cuenta_facturada",
        "/movimientos_cuenta_facturada/movimientos_exportables/cambios",
    }
    if not request.session.get("user_id") and not path.startswith("/static") and path not in allowed:
        return RedirectResponse("/login")
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "secret"),
    https_only=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def format_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


templates.env.filters["money"] = format_money


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    admin_user = os.getenv("ADMIN_USERNAME")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    if admin_user and admin_pass:
        with SessionLocal() as db:
            if not db.query(User).filter(User.username == admin_user).first():
                user = User(
                    username=admin_user,
                    email=admin_email,
                    password_hash=hash_password(admin_pass),
                    is_admin=True,
                    is_active=True,
                )
                db.add(user)
                db.commit()
    start_notification_retention_job()

app.include_router(health_router)
app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(frequents_router)
app.include_router(exportables_router)
app.include_router(invoices_router)
app.include_router(users_router)
app.include_router(billing_info_router)
app.include_router(billing_movements_router)
app.include_router(notifications_router)
app.include_router(inkwell_router)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_notification_retention_job()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Movimientos",
            "header_title": "Movimientos de dinero",
            "user": user,
        },
    )


@app.get("/config.html", response_class=HTMLResponse)
async def config(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "title": "Configuración",
            "header_title": "Configuración",
            "user": user,
        },
    )


@app.get("/accounts.html", response_class=HTMLResponse)
async def accounts_page(request: Request, user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "accounts.html",
        {
            "request": request,
            "title": "Cuentas",
            "header_title": "Cuentas",
            "user": user,
        },
    )


@app.get("/billing.html", response_class=HTMLResponse)
async def billing(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    acc = db.query(Account).filter(Account.is_billing.is_(True)).first()
    if acc:
        title = f"Facturación - {acc.name}"
        header_title = (
            f"Facturación - <span style=\"color:{acc.color}\">{acc.name}</span>"
        )
    else:
        title = "Facturación"
        header_title = "Facturación"
    return templates.TemplateResponse(
        "billing.html",
        {"request": request, "title": title, "header_title": header_title, "user": user},
    )


@app.get("/inkwell.html", response_class=HTMLResponse)
async def inkwell_details_page(
    request: Request, user=Depends(get_current_user)
):
    return templates.TemplateResponse(
        "inkwell_details.html",
        {
            "request": request,
            "title": "Detalles Inkwell",
            "header_title": "Detalles Inkwell",
            "user": user,
        },
    )


@app.get("/invoice/{invoice_id}", response_class=HTMLResponse)
async def invoice_detail(
    request: Request, invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    acc = db.get(Account, inv.account_id)
    symbol = CURRENCY_SYMBOLS.get(acc.currency) if acc else ""
    total = inv.amount + inv.iva_amount
    invoice_data = jsonable_encoder(inv)
    account_data = jsonable_encoder(acc) if acc else None
    return templates.TemplateResponse(
        "invoice_detail.html",
        {
            "request": request,
            "title": "Factura",
            "header_title": "Detalle de factura",
            "invoice": invoice_data,
            "account": account_data,
            "symbol": symbol,
            "total": total,
            "user": user,
        },
    )


@app.get("/invoice/{invoice_id}/edit", response_class=HTMLResponse)
async def edit_invoice_page(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    acc = db.get(Account, inv.account_id)
    symbol = CURRENCY_SYMBOLS.get(acc.currency) if acc else ""
    return templates.TemplateResponse(
        "invoice_edit.html",
        {
            "request": request,
            "title": "Editar factura",
            "header_title": "Editar factura",
            "invoice": inv,
            "account": acc,
            "symbol": symbol,
            "user": user,
        },
    )

@app.post("/invoice/{invoice_id}/delete", dependencies=[Depends(require_admin)])
def delete_invoice_page(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if inv:
        db.delete(inv)
        db.commit()
    return RedirectResponse("/billing.html", status_code=302)
