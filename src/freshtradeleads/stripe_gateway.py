from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess

import stripe


@dataclass(frozen=True)
class CheckoutResult:
    id: str
    url: str


class StripeGateway:
    def __init__(self, secret_key: str, webhook_secret: str, prices: dict[str, str] | None = None):
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.prices = prices or {}

    def create_checkout(self, *, order_id: str, sku: str, name: str, description: str, amount: int, currency: str, success_url: str, cancel_url: str, promotion_id: str | None = None, allow_promotion_codes: bool = True) -> CheckoutResult:
        price_id = self.prices.get(sku)
        if not price_id:
            raise ValueError(f"No Stripe Price configured for {sku}")
        params = dict(
            api_key=self.secret_key,
            mode="payment",
            managed_payments={"enabled":False},
            payment_method_types=["card"],
            line_items=[{"price":price_id,"quantity":1}],
            client_reference_id=order_id,
            metadata={"order_id":order_id,"sku":sku},
            payment_intent_data={"metadata":{"order_id":order_id,"sku":sku}},
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=order_id,
        )
        if promotion_id:
            params["discounts"]=[{"promotion_code":promotion_id}]
        else:
            params["allow_promotion_codes"]=allow_promotion_codes
        session = stripe.checkout.Session.create(**params)
        return CheckoutResult(session.id, session.url)

    def verify_webhook(self, payload: bytes, signature: str):
        return stripe.Webhook.construct_event(payload, signature, self.webhook_secret)


class StripeCLIGateway(StripeGateway):
    """Private-sandbox adapter using Stripe CLI's OAuth-managed restricted credential.

    Production must use StripeGateway with a restricted server-side API key.
    """
    def __init__(self, webhook_secret: str, prices: dict[str, str], project_name: str = "FreshTradeLeads-VM124"):
        super().__init__("cli-managed-sandbox", webhook_secret, prices)
        self.project_name = project_name

    def create_checkout(self, *, order_id: str, sku: str, name: str, description: str, amount: int, currency: str, success_url: str, cancel_url: str, promotion_id: str | None = None, allow_promotion_codes: bool = True) -> CheckoutResult:
        price_id=self.prices.get(sku)
        if not price_id: raise ValueError(f"No Stripe Price configured for {sku}")
        command=["/usr/local/bin/stripe","checkout","sessions","create","--confirm","--project-name",self.project_name,"--mode=payment",f"--client-reference-id={order_id}",f"--success-url={success_url}",f"--cancel-url={cancel_url}",f"--idempotency={order_id}","-d",f"line_items[0][price]={price_id}","-d","line_items[0][quantity]=1","-d","managed_payments[enabled]=false","-d","payment_method_types[0]=card","-d",f"metadata[order_id]={order_id}","-d",f"metadata[sku]={sku}","-d",f"payment_intent_data[metadata][order_id]={order_id}","-d",f"payment_intent_data[metadata][sku]={sku}"]
        if promotion_id: command.extend(["-d",f"discounts[0][promotion_code]={promotion_id}"])
        elif allow_promotion_codes: command.extend(["-d","allow_promotion_codes=true"])
        try:
            completed=subprocess.run(command,capture_output=True,text=True,check=True,timeout=30)
        except subprocess.CalledProcessError as exc:
            detail=(exc.stderr or "Stripe CLI returned an error").strip()[-1000:]
            raise RuntimeError(f"Stripe CLI checkout failed: {detail}") from None
        session=json.loads(completed.stdout)
        if "error" in session:
            raise RuntimeError(f"Stripe Checkout failed: {session['error'].get('message','unknown Stripe error')}")
        if not session.get("id") or not session.get("url"):
            raise RuntimeError("Stripe Checkout returned an incomplete Session")
        return CheckoutResult(session["id"],session["url"])
