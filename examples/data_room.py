"""Set up a data room end to end (async client): create it with folders and an NDA, add documents, invite guests and
print each guest's own link, then read the index and the Q&A.

    HELPRANGE_API_KEY=hr_test_... python examples/data_room.py
"""
import asyncio
import datetime
import os

from helprange import AsyncHelpRange, BadRequestError
from helprange.types import CreateDataRoomBodySettings


async def main() -> None:
    async with AsyncHelpRange() as hr:
        # NDAs need the Max plan (or the Deal Room Pass / trial); ndas.list() says whether the team has them.
        ndas = await hr.ndas.list()
        settings: CreateDataRoomBodySettings = {"download": False, "watermark": True}
        if ndas["nda_available"]:
            if ndas["ndas"]:
                settings["nda_id"] = ndas["ndas"][0]["id"]
            else:
                settings["nda"] = True
                settings["nda_template"] = "investor"

        room = await hr.data_rooms.create(
            name=f"Project Falcon {datetime.date.today()}",
            folders=["1. Corporate", "2. Financials", "3. Legal"],
            settings=settings,
        )
        print(f"Created {room['name']!r} (id {room['id']}) – guest link {room['links']['guest_link']}")

        # The two newest documents go into the "2. Financials" folder
        documents = (await hr.documents.list())["documents"]
        await hr.data_rooms.documents.add(room["id"], document_ids=[d["id"] for d in documents[:2]],
                                          folder_id=room["folders"][1]["id"])

        for email in ("jane@example.com", "max@example.com"):
            try:  # test mode only accepts reserved domains such as example.com
                guest = await hr.data_rooms.guests.invite(room["id"], email=email)
                print(f"{guest['email']}: {guest['link']}" + (" (already a guest)" if guest["already_a_guest"] else ""))
            except BadRequestError as e:
                if e.code != "sandbox_email_domain":
                    raise
                print("Use an example.com address in test mode")

        for g in (await hr.data_rooms.guests.list(room["id"]))["guests"]:
            print(g["email"], "→", g["link"])

        index = await hr.data_rooms.get_index(room["id"])
        for node in index["index"]:
            print(node["number"], node.get("name"))

        print(await hr.data_rooms.questions.list(room["id"], status="open"))

        # Clean up: remove a guest; deleting the room needs an explicit confirm=True
        await hr.data_rooms.guests.remove(room["id"], email="max@example.com")
        if os.environ.get("DELETE_ROOM") == "1":
            await hr.data_rooms.delete(room["id"], confirm=True)


asyncio.run(main())
