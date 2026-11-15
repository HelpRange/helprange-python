"""The endpoints added with spec 2026-11-15: data rooms CRUD + sub-resources, NDAs, links, webhook endpoints."""
import json


def calls(rec):
    return [f"{r.method} {r.url.path}" + (f"?{r.url.query.decode()}" if r.url.query else "") for r in rec.requests]


def body(r):
    return json.loads(r.content) if r.content else None


def test_data_room_create_update_delete_ndas(client, rec):
    rec.add(201, {"id": 12, "name": "Falcon", "links": {"guest_link": "https://www.helprange.com/r/abc"}})
    rec.add(200, {}).add(200, {"deleted": True, "id": 12, "name": "Falcon"}).add(200, {"nda_available": True})
    room = client.data_rooms.create(name="Falcon", folders=["Legal", "Financials"],
                                    settings={"nda": True, "nda_template": "investor", "download": False})
    assert room["links"]["guest_link"].endswith("/r/abc")
    client.data_rooms.update(12, name="Falcon II", settings={"watermark": True})
    assert client.data_rooms.delete(12, confirm=True)["deleted"] is True
    client.ndas.list()
    assert calls(rec) == ["POST /api/v2/data-rooms", "POST /api/v2/data-rooms/12", "POST /api/v2/data-rooms/12/delete",
                          "GET /api/v2/ndas"]
    assert [body(r) for r in rec.requests] == [
        {"name": "Falcon", "folders": ["Legal", "Financials"], "settings": {"nda": True, "nda_template": "investor", "download": False}},
        {"name": "Falcon II", "settings": {"watermark": True}},
        {"confirm": True},
        None,
    ]


def test_data_room_sub_resources(client, rec):
    for _ in range(8):
        rec.add(200, {})
    client.data_rooms.guests.list(12)
    client.data_rooms.guests.invite(12, email="jane@example.com", send_invite=False)
    client.data_rooms.guests.remove(12, guest_id=5)
    client.data_rooms.documents.list(12)
    client.data_rooms.documents.add(12, document_ids=[1, 2])
    client.data_rooms.documents.remove(12, document_ids=[2])
    client.data_rooms.folders.list(12)
    client.data_rooms.questions.list(12, status="open")
    assert calls(rec) == [
        "GET /api/v2/data-rooms/12/guests",
        "POST /api/v2/data-rooms/12/guests",
        "POST /api/v2/data-rooms/12/guests/remove",
        "GET /api/v2/data-rooms/12/documents",
        "POST /api/v2/data-rooms/12/documents",
        "POST /api/v2/data-rooms/12/documents/remove",
        "GET /api/v2/data-rooms/12/folders",
        "GET /api/v2/data-rooms/12/questions?status=open",
    ]
    assert body(rec.requests[1]) == {"email": "jane@example.com", "send_invite": False}
    assert body(rec.requests[2]) == {"guest_id": 5}


def test_links_list_and_views(client, rec):
    rec.add(200, {"links": [{"id": 264}], "page": 2, "limit": 50, "total": 51, "next_page": None})
    rec.add(200, {"link": {"id": 264}, "views": [{"viewer": "anna@acme.com"}], "page": 1, "limit": 100, "total": 1,
                  "next_page": None})
    assert client.links.list(document_id=250, room_id=12, status="active", page=2, limit=50)["links"][0]["id"] == 264
    assert client.links.views(264, limit=100)["views"][0]["viewer"] == "anna@acme.com"
    assert calls(rec) == ["GET /api/v2/links?document_id=250&room_id=12&status=active&page=2&limit=50",
                          "GET /api/v2/links/264/views?limit=100"]


def test_webhook_endpoints(client, rec):
    for _ in range(9):
        rec.add(200, {"id": 3, "secret": "whsec_x"})
    hr = client.webhook_endpoints
    hr.list()
    assert hr.create(url="https://example.com/h")["secret"] == "whsec_x"
    hr.get(3)
    hr.update(3, enabled=True)
    hr.rotate_secret(3)
    hr.send_test(3)
    hr.deliveries(3, status="failed", limit=10)
    hr.redeliver(3, 99)
    hr.delete(3)
    assert calls(rec) == [
        "GET /api/v2/webhook-endpoints",
        "POST /api/v2/webhook-endpoints",
        "GET /api/v2/webhook-endpoints/3",
        "POST /api/v2/webhook-endpoints/3",
        "POST /api/v2/webhook-endpoints/3/rotate-secret",
        "POST /api/v2/webhook-endpoints/3/test",
        "GET /api/v2/webhook-endpoints/3/deliveries?status=failed&limit=10",
        "POST /api/v2/webhook-endpoints/3/deliveries/99/redeliver",
        "POST /api/v2/webhook-endpoints/3/delete",
    ]
    assert rec.requests[4].headers.get("idempotency-key") and not rec.requests[4].content
