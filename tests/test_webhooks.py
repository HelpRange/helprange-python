import pytest

from helprange import WebhookVerificationError, compute_signature, sign_webhook_payload, verify_webhook

# Vector computed with HelpRange's server code (plus/webhooks.sign).
BODY = b'{"id":"evt_1","event":"document.opened","api_version":"2026-11-15","created_at":"2026-11-15T09:12:03Z","data":{"file_id":123}}'
T = 1763197923
SIG = "b27214711a29d4f299074d7cb70ccd777783a9cec2bf0da880a4cf8f8d5f3867"
SECRET = "whsec_test_secret"


def test_matches_server_signature():
    assert compute_signature(BODY, SECRET, T) == SIG
    event = verify_webhook(BODY, {"HelpRange-Signature": f"t={T},v1={SIG}"}, SECRET, now=T + 10)
    assert event["id"] == "evt_1" and event["data"]["file_id"] == 123


def test_str_payload_case_insensitive_headers_and_rotation():
    header = f"t={T},v1={compute_signature(BODY, 'whsec_new', T)},v1={SIG}"
    assert verify_webhook(BODY.decode(), {"helprange-signature": header}, SECRET, now=T)["event"] == "document.opened"
    verify_webhook(BODY, {"HELPRANGE-SIGNATURE": header}, ["whsec_other", "whsec_new"], now=T)


@pytest.mark.parametrize("headers,secret,now", [
    ({}, SECRET, T),
    ({"HelpRange-Signature": f"v1={SIG}"}, SECRET, T),
    ({"HelpRange-Signature": f"t=abc,v1={SIG}"}, SECRET, T),
    ({"HelpRange-Signature": f"t={T},v1={SIG}"}, "whsec_wrong", T),
    ({"HelpRange-Signature": f"t={T},v1={SIG}"}, SECRET, T + 301),
    ({"HelpRange-Signature": f"t={T},v1=żółw"}, SECRET, T),
    ({"HelpRange-Signature": f"t={T},v1={SIG}"}, [], T),
])
def test_rejects(headers, secret, now):
    with pytest.raises(WebhookVerificationError):
        verify_webhook(BODY, headers, secret, now=now)


def test_tampered_body_and_tolerance():
    with pytest.raises(WebhookVerificationError):
        verify_webhook(BODY + b" ", {"HelpRange-Signature": f"t={T},v1={SIG}"}, SECRET, now=T)
    verify_webhook(BODY, {"HelpRange-Signature": f"t={T},v1={SIG}"}, SECRET, now=T + 301, tolerance=600)


def test_sign_round_trip():
    assert verify_webhook(BODY, {"HelpRange-Signature": sign_webhook_payload(BODY, SECRET)}, SECRET)["id"] == "evt_1"
