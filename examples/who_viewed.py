"""Who opened a document, through which share link, when and for how long.

    HELPRANGE_API_KEY=hr_live_... python examples/who_viewed.py 250
"""
import sys
from typing import Optional

from helprange import HelpRange

document_id = int(sys.argv[1])
hr = HelpRange()

doc = hr.documents.get(document_id)
print(f"{doc['name']}: {doc['views']} views, {doc['downloads']} downloads, {doc['total_seconds_read'] or 0}s read")

# Every share link of the document (links.list also filters by folder_id, room_id, label, status, created_*)
for link in hr.links.list(document_id=document_id, status="all", limit=200)["links"]:
    print(f"\nLink {link['label']!r} ({link['status']}) – {link['views']} views – {link['url']}")
    page: Optional[int] = 1
    while page is not None:  # every view through this one link
        res = hr.links.views(link["id"], page=page, limit=100)
        for v in res["views"]:
            print(f"  {v['opened_at']}  {v['viewer']:<30}  {v['seconds_read'] or 0}s  {v['pages_read']} pages"
                  f"  {v['country'] or ''}" + ("  downloaded" if v["downloaded"] else ""))
        page = res["next_page"]

for p in doc["avg_seconds_per_page"] or []:
    print(f"page {p['page']}: {p['avg_seconds']}s on average")
