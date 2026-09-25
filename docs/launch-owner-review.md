# Launch owner review

This is a reusable operational checklist, not legal advice. Complete it before enabling live payments and revisit it as the deployment evolves.

- Confirm the public-facing business name is correctly presented as **FreshTradeLeads** and decide whether an individual/legal operator name must appear in Terms, receipts, tax material, or checkout.
- Review Terms for governing law, limitation-of-liability, acceptable-use, data accuracy, and compliance responsibilities for phone/email outreach.
- Approve the digital-product refund policy, including the “generally final after delivery” wording and the promised remedy for unavailable, defective, or misdescribed files.
- Approve Privacy disclosures for first-party funnel events, UTM storage, order email, Stripe, Cloudflare, server logs, retention periods, and any California privacy obligations that apply.
- Confirm Stripe Checkout/statement descriptor, customer receipt settings, and the deployed support address.
- Confirm the public-record/source description is accurate, the CSLB non-affiliation disclaimer is sufficiently prominent, and the current-status verification direction is acceptable.
- Decide and document retention/deletion periods for order records, email addresses, funnel events, logs, and generated paid reports.
- Confirm sales-tax treatment and whether Stripe Tax or manual tax handling is required for downloadable B2B data products.
- Send a real external message to the support address and verify delivery.
- Confirm the promotion's expiration and redemption cap before launch.
- Decide whether “first purchase” must be strictly enforced. Stripe's first-time restriction accepts anonymous Guest Customer sessions; strict enforcement requires stable Stripe Customer reuse or collecting identity before Checkout.
- Confirm full refunds are initiated through Stripe and verify the resulting `charge.refunded` webhook changes the order to `refunded` and revokes download access. Partial refunds remain recorded without shortening the existing download period.
- Rotate the retained live Stripe API credential after the validation period or immediately if exposure is suspected.
