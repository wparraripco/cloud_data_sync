"""
Azure Function — Monday.com webhook receiver.

Listens for three Monday.com webhook events:
  create_item          → upsert item into core + bridge tables
  change_column_value  → upsert item into core + bridge tables
  delete_item          → delete item + its bridge rows

Monday sends a challenge POST when a webhook is first registered.
This function handles that automatically.

Required app settings (env vars in Azure):
  MONDAY_API_KEY
  SQL_SERVER
  SQL_UID  (optional)
  SQL_PWD  (optional)
"""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func
import requests
from dotenv import load_dotenv

import monday_db as db

load_dotenv(override=True)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_KEY = os.environ["MONDAY_API_KEY"]
BOARD1_ID      = "18415335792"
BOARD2_ID      = "18415335878"

_HEADERS = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type":  "application/json",
    "API-Version":   "2024-01",
}

# ---------------------------------------------------------------------------
# Monday API — fetch a single item
# ---------------------------------------------------------------------------

_ITEM_GQL = """
query ($itemId: [ID!]!) {
  items(ids: $itemId) {
    id name created_at updated_at
    group { id title }
    column_values {
      id type value
      ... on BoardRelationValue { linked_item_ids }
    }
  }
}
"""

_CONTACT_IDS_GQL = """
{
  boards(ids: [%s]) {
    items_page(limit: 500) {
      items { id }
    }
  }
}
""" % BOARD2_ID


def _gql(query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        MONDAY_API_URL,
        headers=_HEADERS,
        json={"query": query, "variables": variables or {}},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"Monday GraphQL error: {body['errors']}")
    return body["data"]


def fetch_item(item_id: int) -> dict | None:
    data  = _gql(_ITEM_GQL, {"itemId": [str(item_id)]})
    items = data.get("items", [])
    return items[0] if items else None


def fetch_contact_ids() -> set[int]:
    data = _gql(_CONTACT_IDS_GQL)
    items = data["boards"][0]["items_page"]["items"]
    return {int(i["id"]) for i in items}

# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

@app.route(route="monday_webhook", methods=["POST"])
def monday_webhook(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON", status_code=400)

    # Monday sends a challenge when the webhook is first registered
    if "challenge" in body:
        return func.HttpResponse(
            json.dumps({"challenge": body["challenge"]}),
            mimetype="application/json",
            status_code=200,
        )

    event = body.get("event", {})
    event_type = event.get("type")
    board_id   = str(event.get("boardId", ""))
    item_id    = int(event.get("pulseId") or event.get("itemId") or 0)

    if not item_id:
        return func.HttpResponse("Missing item ID", status_code=400)

    logging.info(f"Monday webhook: {event_type} | board={board_id} | item={item_id}")

    try:
        with db.get_connection() as conn:
            cur = conn.cursor()

            if event_type in ("delete_pulse", "delete_item"):
                _handle_delete(cur, board_id, item_id)

            elif event_type in ("create_pulse", "create_item",
                                "update_column_value", "change_column_value"):
                _handle_upsert(cur, board_id, item_id)

            else:
                logging.info(f"Unhandled event type: {event_type} — ignoring.")
                return func.HttpResponse("Ignored", status_code=200)

            conn.commit()

    except Exception as exc:
        logging.exception(f"Error processing webhook: {exc}")
        return func.HttpResponse(f"Error: {exc}", status_code=500)

    return func.HttpResponse("OK", status_code=200)


def _handle_delete(cur, board_id: str, item_id: int) -> None:
    if board_id == BOARD1_ID:
        db.delete_property(cur, item_id)
        logging.info(f"Deleted property {item_id}")
    elif board_id == BOARD2_ID:
        db.delete_contact(cur, item_id)
        logging.info(f"Deleted contact {item_id}")


def _handle_upsert(cur, board_id: str, item_id: int) -> None:
    item = fetch_item(item_id)
    if not item:
        logging.warning(f"Item {item_id} not found in Monday — skipping.")
        return

    if board_id == BOARD1_ID:
        contact_ids = fetch_contact_ids()
        db.upsert_property(cur, item, contact_ids)
        logging.info(f"Upserted property {item_id}")
    elif board_id == BOARD2_ID:
        db.upsert_contact(cur, item)
        logging.info(f"Upserted contact {item_id}")
