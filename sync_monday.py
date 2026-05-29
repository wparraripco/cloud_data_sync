"""
Monday.com -> Ripco_Monday_Data full backfill sync.

Boards:
  Board 1 — [WP Testing] - Board 1  (ID: 18415335792)
  Board 2 — [WP Testing] - Board 2  (ID: 18415335878)

Required env vars:
  MONDAY_API_KEY  — Monday.com API token
  SQL_SERVER      — e.g. MYSERVER or MYSERVER\INSTANCE
  SQL_UID         — (optional) SQL login; omit for Windows auth
  SQL_PWD         — (optional) SQL password
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

import monday_db as db

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_KEY = os.environ["MONDAY_API_KEY"]

BOARD1_ID = "18415335792"
BOARD2_ID = "18415335878"

_HEADERS = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type":  "application/json",
    "API-Version":   "2024-01",
}

# ---------------------------------------------------------------------------
# Monday GraphQL client
# ---------------------------------------------------------------------------

_ITEMS_GQL = """
query ($boardId: [ID!]!, $cursor: String) {
  boards(ids: $boardId) {
    items_page(limit: 500, cursor: $cursor) {
      cursor
      items {
        id name created_at updated_at
        group { id title }
        column_values {
          id type value
          ... on BoardRelationValue { linked_item_ids }
        }
      }
    }
  }
}
"""

_USERS_GQL = """
{
  users(limit: 1000, kind: all) {
    id name email title enabled is_admin is_guest photo_thumb
  }
}
"""


def _gql(query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        MONDAY_API_URL,
        headers=_HEADERS,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"Monday GraphQL error: {body['errors']}")
    return body["data"]


def fetch_board_items(board_id: str) -> list[dict]:
    items, cursor = [], None
    while True:
        data   = _gql(_ITEMS_GQL, {"boardId": [board_id], "cursor": cursor})
        page   = data["boards"][0]["items_page"]
        items.extend(page["items"])
        cursor = page.get("cursor")
        if not cursor:
            break
    return items


def fetch_users() -> list[dict]:
    return _gql(_USERS_GQL)["users"]

# ---------------------------------------------------------------------------
# Sync functions
# ---------------------------------------------------------------------------

def sync_users(cur) -> None:
    print("  Syncing lookup.users...")
    users = fetch_users()
    for u in users:
        db.upsert_user(cur, u)
    print(f"    {len(users)} users upserted.")


def sync_contacts(cur) -> set[int]:
    print("  Syncing core.test_contacts...")
    items = fetch_board_items(BOARD2_ID)
    for item in items:
        db.upsert_contact(cur, item)
    print(f"    {len(items)} contacts upserted.")
    return {int(i["id"]) for i in items}


def sync_properties(cur, contact_ids: set[int]) -> None:
    print("  Syncing core.test_properties...")
    items = fetch_board_items(BOARD1_ID)
    for item in items:
        db.upsert_property(cur, item, contact_ids)
    print(f"    {len(items)} properties upserted.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Connecting to Ripco_Monday_Data on {os.environ['SQL_SERVER']}...")
    with db.get_connection() as conn:
        cur = conn.cursor()
        try:
            sync_users(cur)
            contact_ids = sync_contacts(cur)
            sync_properties(cur, contact_ids)
            conn.commit()
            print("Done — all changes committed.")
        except Exception as exc:
            conn.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
