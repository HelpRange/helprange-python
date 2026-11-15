"""Manage the team's webhook endpoint through the API: create it (the secret is shown once), send a test event,
look at the delivery log, redeliver a failure, rotate the secret.

    HELPRANGE_API_KEY=hr_live_... python examples/webhook_endpoints.py https://example.com/webhooks/helprange
"""
import sys

from helprange import ConflictError, HelpRange

hr = HelpRange()
url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com/webhooks/helprange"

try:
    created = hr.webhook_endpoints.create(url=url)
    endpoint_id = created["id"]
    print(f"Created endpoint {endpoint_id}. Store this secret now – it is not shown again: {created['secret']}")
except ConflictError:
    # A team has one endpoint: reuse it and point it at the new URL
    endpoint_id = hr.webhook_endpoints.list()["webhook_endpoints"][0]["id"]
    updated = hr.webhook_endpoints.update(endpoint_id, url=url, enabled=True)
    print(f"Updated endpoint {endpoint_id} → {updated['url']}")

test = hr.webhook_endpoints.send_test(endpoint_id)
print(f"Test event {test['event_id']}: " + ("delivered" if test["delivered"] else f"failed ({test.get('last_error')})"))

log = hr.webhook_endpoints.deliveries(endpoint_id, status="failed", limit=20)
print(f"{len(log['deliveries'])} failed deliveries in the last {log['retention_days']} days")
if log["deliveries"]:
    again = hr.webhook_endpoints.redeliver(endpoint_id, log["deliveries"][0]["id"])
    print(f"Redelivered {again['event_id']}: {'ok' if again['delivered'] else 'failed again'}")

# Rotate the secret: for 24 hours HelpRange signs with both the old and the new one
rotated = hr.webhook_endpoints.rotate_secret(endpoint_id)
print(f"New secret: {rotated['secret']} (old one valid until {rotated['previous_secret_expires_at']})")
