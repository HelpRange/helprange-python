"""A webhook receiver on the standard library's http.server.

Point Settings → Integrations → Webhook URL at it and use "Send test event" in the delivery log.

    HELPRANGE_WEBHOOK_SECRET=whsec_... python examples/webhook_server.py
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from helprange import WebhookVerificationError, verify_webhook

SECRET = os.environ["HELPRANGE_WEBHOOK_SECRET"]
seen: set[str] = set()  # deduplicate on the event id (retries carry the same id) – use your database in production


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            event = verify_webhook(raw, self.headers, SECRET)
        except WebhookVerificationError:
            self.send_response(400)
            self.end_headers()
            return
        if event["id"] not in seen:
            seen.add(event["id"])
            if event["event"] == "document.opened":
                print(f"{event['data'].get('viewer')} opened {event['data'].get('document')}")
        self.send_response(200)  # answer 2xx within 10 seconds
        self.end_headers()


HTTPServer(("", 3000), Handler).serve_forever()
