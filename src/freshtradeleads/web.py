from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select

from .config import WebSettings, web_settings
from .db import get_engine
from .exporter import export_xlsx
from .orders import UnknownProductError, authorize_download, create_order, fulfill_verified_event, order_status, token_hash, track_event
from .products import REPORT_COLUMNS, current_preview, historical_sample, inventory
from .schema import download_tokens, metadata, orders
from .stripe_gateway import StripeCLIGateway, StripeGateway

PACKAGE=Path(__file__).parent
UTM_KEYS=("utm_source","utm_medium","utm_campaign","utm_content","utm_term")
LOG=logging.getLogger("freshtradeleads.web")


def _sample_file(engine, data_dir: Path):
    path=data_dir/"web"/"sample"/"freshtradeleads_historical_sample.xlsx"
    with engine.connect() as conn: snapshot, rows=historical_sample(conn)
    notice=("This free sample contains intentionally older historical records and is not current paid inventory. It demonstrates the data fields and report format supplied by FreshTradeLeads. Underlying licensing information originates from official California contractor licensing records. FreshTradeLeads is independent and is not affiliated with or endorsed by CSLB. Licensing status can change and should be independently verified with CSLB.")
    export_xlsx(rows,REPORT_COLUMNS,path,{"generated_at":datetime.now(timezone.utc).isoformat(),"source_as_of":snapshot["newest_issue_date"].isoformat(),"source_sha256":snapshot["sha256"]},info_sheet_name="About This Sample",notice=notice)
    return path, rows


def create_app(*, engine=None, settings: WebSettings | None=None, gateway=None):
    settings=settings or web_settings(); engine=engine or get_engine(settings.database_url)
    metadata.create_all(engine)
    app=FastAPI(title="FreshTradeLeads",docs_url=None,redoc_url=None,openapi_url=None)
    app.state.engine=engine; app.state.settings=settings
    if gateway is None and settings.stripe_ready:
        gateway=StripeCLIGateway(settings.stripe_webhook_secret,settings.stripe_prices) if settings.stripe_use_cli else StripeGateway(settings.stripe_secret_key,settings.stripe_webhook_secret,settings.stripe_prices)
    app.state.gateway=gateway
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(SessionMiddleware,secret_key=settings.session_secret,same_site="lax",https_only=settings.secure_cookies,max_age=60*60*24*30)
    app.mount("/static",StaticFiles(directory=PACKAGE/"static"),name="static")
    templates=Jinja2Templates(directory=PACKAGE/"templates")

    @app.middleware("http")
    async def headers(request, call_next):
        if request.method in {"POST","PUT","PATCH"} and int(request.headers.get("content-length","0") or 0) > 1_048_576:
            return JSONResponse({"detail":"Request too large"},status_code=413)
        response=await call_next(request)
        response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"strict-origin-when-cross-origin","Permissions-Policy":"camera=(), microphone=(), geolocation=()","Content-Security-Policy":"default-src 'self'; script-src 'self' https://connect.facebook.net; style-src 'self'; img-src 'self' https://www.facebook.com; connect-src 'self' https://www.facebook.com https://connect.facebook.net; form-action 'self' https://checkout.stripe.com; frame-ancestors 'none'; base-uri 'self'","Cross-Origin-Opener-Policy":"same-origin","X-Permitted-Cross-Domain-Policies":"none"})
        if settings.secure_cookies: response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
        return response

    def context(request, **extra):
        return {"request":request,"year":datetime.now().year,"meta_pixel_id":settings.meta_pixel_id,**extra}

    @app.get("/",response_class=HTMLResponse)
    def landing(request: Request):
        visitor=request.session.setdefault("visitor_id",secrets.token_hex(16)); request.session.setdefault("csrf",secrets.token_urlsafe(24))
        utm=request.session.get("utm",{})
        for key in UTM_KEYS:
            if request.query_params.get(key): utm[key]=request.query_params[key][:250]
        request.session["utm"]=utm
        requested=request.query_params.get("promo","").upper()
        if requested and requested == (settings.promotion_code or "").upper(): request.session["promotion_code"]=settings.promotion_code
        elif requested: request.session.pop("promotion_code",None)
        with engine.begin() as conn:
            snapshot,items=inventory(conn); preview=current_preview(conn); track_event(conn,"landing_viewed",visitor_id=visitor,utm=utm)
        return templates.TemplateResponse(request,"index.html",context(request,snapshot=snapshot,products=items,preview=preview,csrf=request.session["csrf"],stripe_ready=bool(app.state.gateway),cancelled=request.query_params.get("checkout")=="cancelled",promotion_code=settings.promotion_code))

    @app.get("/sample/download")
    def sample(request: Request):
        path, rows=_sample_file(engine,settings.data_dir)
        with engine.begin() as conn: track_event(conn,"free_sample_downloaded",visitor_id=request.session.get("visitor_id"),utm=request.session.get("utm"),metadata={"records":len(rows)})
        return FileResponse(path,filename="FreshTradeLeads_Historical_C10_Sample.xlsx",media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.post("/checkout/{sku}")
    def checkout(request: Request, sku: str, csrf: str=Form(...)):
        if not secrets.compare_digest(csrf,request.session.get("csrf", "")): raise HTTPException(403,"Invalid request token")
        if not app.state.gateway: return templates.TemplateResponse(request,"checkout_unavailable.html",context(request),status_code=503)
        promo=request.session.get("promotion_code")
        approved=bool(promo and settings.promotion_code and secrets.compare_digest(promo,settings.promotion_code))
        try: order_id,token,result=create_order(engine,sku,utm=request.session.get("utm",{}),visitor_id=request.session.get("visitor_id"),base_url=settings.base_url,gateway=app.state.gateway,promotion_code=settings.promotion_code if approved else None,promotion_id=settings.stripe_promotion_id if approved else None,promotion_percent=settings.promotion_percent)
        except UnknownProductError: raise HTTPException(404,"Unknown product")
        except RuntimeError:
            LOG.exception("Stripe Checkout creation failed")
            return templates.TemplateResponse(request,"checkout_unavailable.html",context(request),status_code=503)
        return RedirectResponse(result.url,status_code=303)

    @app.post("/webhooks/stripe")
    async def webhook(request: Request):
        if not app.state.gateway: raise HTTPException(503,"Stripe is not configured")
        payload=await request.body(); signature=request.headers.get("stripe-signature","")
        try: event=app.state.gateway.verify_webhook(payload,signature); result=fulfill_verified_event(engine,event,data_dir=settings.data_dir,download_days=settings.download_days,approved_promotion_id=settings.stripe_promotion_id,approved_promotion_code=settings.promotion_code)
        except Exception as exc:
            LOG.warning("Stripe webhook rejected: %s",type(exc).__name__)
            raise HTTPException(400,"Invalid webhook") from None
        return JSONResponse(result)

    @app.get("/order/{order_id}/success",response_class=HTMLResponse)
    def success(request: Request, order_id: str, token: str="", session_id: str=""):
        order=order_status(engine,order_id)
        if not order: raise HTTPException(404,"Order not found")
        valid_token=False
        if token:
            with engine.connect() as conn: valid_token=conn.execute(select(download_tokens.c.order_id).where(download_tokens.c.token_hash==token_hash(token),download_tokens.c.order_id==order_id)).scalar_one_or_none() is not None
        return templates.TemplateResponse(request,"success.html",context(request,order=order,token=token if valid_token else "",session_id=session_id))

    @app.get("/download/{token}/{fmt}")
    def paid_download(token: str, fmt: str):
        path=authorize_download(engine,token,fmt,data_dir=settings.data_dir)
        if not path or not path.exists(): raise HTTPException(404,"This download link is invalid, expired, or not yet authorized")
        media="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt=="xlsx" else "text/csv"
        return FileResponse(path,filename=f"FreshTradeLeads_C10_Southern_California.{fmt}",media_type=media)

    pages={"methodology":("Methodology & Data","methodology.html"),"privacy":("Privacy","privacy.html"),"terms":("Terms","terms.html"),"refunds":("Refund Policy","refunds.html"),"about":("About","about.html")}
    for route,(title,template) in pages.items():
        def view(request: Request, _title=title, _template=template): return templates.TemplateResponse(request,_template,context(request,title=_title))
        app.add_api_route(f"/{route}",view,response_class=HTMLResponse,name=route)

    @app.get("/health")
    def health(): return {"status":"ok"}
    return app


def run():
    uvicorn.run(create_app(),host="127.0.0.1",port=8080,log_level="info")
