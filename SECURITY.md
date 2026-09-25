# Security policy

This archived project does not receive security releases on a guaranteed
schedule. Do not open a public issue for a vulnerability that could expose
credentials, payment information, or personal data. Use GitHub's private
vulnerability-reporting feature if it is enabled for this repository.

Deployments must provide secrets outside Git, restrict database access, validate
Stripe webhook signatures, use HTTPS, and review all defaults before accepting
traffic or payments.
