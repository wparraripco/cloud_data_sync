"""
Monday.com -> RipcoMonday SQL Server sync

Boards:
  Board 1 — [WP Testing] - Board 1  (ID: 18415335792)
  Board 2 — [WP Testing] - Board 2  (ID: 18415335878)

Tables:
  lookup.users
  core.test_properties
  core.test_contacts
  bridge.properties_contacts
  bridge.users_properties
  bridge.users_contacts

Required env vars:
  MONDAY_API_KEY  — Monday.com API token
  SQL_SERVER      — e.g. MYSERVER or MYSERVER\INSTANCE
  SQL_UID         — (optional) SQL login; omit for Windows auth
  SQL_PWD         — (optional) SQL password
"""

from __future__ import annotations

import json
import os
import sys

import pyodbc
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_KEY = os.environ["MONDAY_API_KEY"]
SQL_SERVER     = os.environ["SQL_SERVER"]

_uid = os.environ.get("SQL_UID")
_pwd = os.environ.get("SQL_PWD")
SQL_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SQL_SERVER};DATABASE=Ripco_Monday_Data;"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    + (f"UID={_uid};PWD={_pwd};" if _uid else "Trusted_Connection=yes;")
)

BOARD1_ID = "18415335792"
BOARD2_ID = "18415335878"

# Monday column IDs
B1_PERSON   = "person"
B1_LOCATION = "location_mm3spvjs"
B1_STATUS   = "status"
B1_DATE     = "date4"
B1_RELATION = "board_relation_mm3tq3kq"

B2_PERSON = "person"
B2_DATE   = "date4"
B2_EMAIL  = "email_mm3sbzqz"

# ---------------------------------------------------------------------------
# Monday GraphQL client
# ---------------------------------------------------------------------------

_HEADERS = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type":  "application/json",
    "API-Version":   "2024-01",
}

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
# Column value parsers
# ---------------------------------------------------------------------------

def _j(raw):
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or raw in ("null", ""):
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_people(raw) -> list[int]:
    v = _j(raw)
    if not v:
        return []
    if isinstance(v, list):
        return [int(p["id"]) for p in v if p.get("kind") == "person"]
    return [
        int(p["id"])
        for p in v.get("personsAndTeams", [])
        if p.get("kind") == "person"
    ]


def _str(val) -> str | None:
    if val is None:
        return None
    return str(val) if not isinstance(val, str) else val


def parse_location(raw) -> dict:
    v = _j(raw)
    if not v:
        return {}
    return {
        "address":  _str(v.get("address")),
        "city":     _str(v.get("city")),
        "country":  _str(v.get("country")),
        "lat":      v.get("lat"),
        "lng":      v.get("lng"),
        "place_id": _str(v.get("placeId")),
    }


def parse_status(raw: str | None) -> str | None:
    v = _j(raw)
    return v.get("label") if v else None


def parse_date(raw: str | None) -> str | None:
    v = _j(raw)
    return v.get("date") if v else None


def parse_relation(raw) -> list[int]:
    if isinstance(raw, list):
        result = []
        for x in raw:
            if isinstance(x, (str, int)):
                result.append(int(x))
            elif isinstance(x, dict) and "id" in x:
                result.append(int(x["id"]))
        return result
    v = _j(raw)
    if not v:
        return []
    if isinstance(v, list):
        return parse_relation(v)
    return [int(p["linkedPulseId"]) for p in v.get("linkedPulseIds", [])]


def parse_email(raw: str | None) -> tuple[str | None, str | None]:
    v = _j(raw)
    if not v:
        return None, None
    return v.get("email"), v.get("text")


def col_map(item: dict) -> dict:
    result = {}
    for cv in item["column_values"]:
        if cv.get("linked_item_ids") is not None:
            result[cv["id"]] = cv["linked_item_ids"]
        else:
            result[cv["id"]] = cv.get("value")
    return result

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_UPSERT_USER = """
MERGE lookup.users WITH (HOLDLOCK) AS t
USING (SELECT ? AS user_id, ? AS name, ? AS email, ? AS title,
              ? AS is_enabled, ? AS is_admin, ? AS is_guest,
              ? AS photo_thumb_url) AS s
ON t.user_id = s.user_id
WHEN MATCHED THEN UPDATE SET
    name=s.name, email=s.email, title=s.title,
    is_enabled=s.is_enabled, is_admin=s.is_admin, is_guest=s.is_guest,
    photo_thumb_url=s.photo_thumb_url, synced_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (user_id, name, email, title, is_enabled, is_admin, is_guest,
     photo_thumb_url, synced_at)
VALUES (s.user_id, s.name, s.email, s.title,
        s.is_enabled, s.is_admin, s.is_guest,
        s.photo_thumb_url, SYSUTCDATETIME());
"""

_UPSERT_B1 = """
MERGE core.test_properties WITH (HOLDLOCK) AS t
USING (SELECT ? AS item_id, ? AS group_id, ? AS group_name, ? AS name,
              ? AS location_address, ? AS location_city, ? AS location_country,
              ? AS location_lat, ? AS location_lng, ? AS location_place_id,
              ? AS status, ? AS date, ? AS created_at, ? AS updated_at) AS s
ON t.item_id = s.item_id
WHEN MATCHED THEN UPDATE SET
    group_id=s.group_id, group_name=s.group_name, name=s.name,
    location_address=s.location_address, location_city=s.location_city,
    location_country=s.location_country, location_lat=s.location_lat,
    location_lng=s.location_lng, location_place_id=s.location_place_id,
    status=s.status, date=s.date,
    created_at=s.created_at, updated_at=s.updated_at,
    synced_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (item_id, group_id, group_name, name,
     location_address, location_city, location_country,
     location_lat, location_lng, location_place_id,
     status, date, created_at, updated_at, synced_at)
VALUES (s.item_id, s.group_id, s.group_name, s.name,
        s.location_address, s.location_city, s.location_country,
        s.location_lat, s.location_lng, s.location_place_id,
        s.status, s.date, s.created_at, s.updated_at, SYSUTCDATETIME());
"""

_UPSERT_B2 = """
MERGE core.test_contacts WITH (HOLDLOCK) AS t
USING (SELECT ? AS item_id, ? AS group_id, ? AS group_name, ? AS name,
              ? AS date, ? AS email, ? AS email_label,
              ? AS created_at, ? AS updated_at) AS s
ON t.item_id = s.item_id
WHEN MATCHED THEN UPDATE SET
    group_id=s.group_id, group_name=s.group_name, name=s.name,
    date=s.date, email=s.email, email_label=s.email_label,
    created_at=s.created_at, updated_at=s.updated_at,
    synced_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (item_id, group_id, group_name, name, date, email, email_label,
     created_at, updated_at, synced_at)
VALUES (s.item_id, s.group_id, s.group_name, s.name,
        s.date, s.email, s.email_label,
        s.created_at, s.updated_at, SYSUTCDATETIME());
"""

_INS_RELATION = """
IF NOT EXISTS (
    SELECT 1 FROM bridge.properties_contacts
     WHERE property_item_id = ? AND contact_item_id = ?
)
INSERT INTO bridge.properties_contacts (property_item_id, contact_item_id)
VALUES (?, ?);
"""

_INS_B1_PERSON = """
IF NOT EXISTS (
    SELECT 1 FROM bridge.users_properties WHERE item_id = ? AND user_id = ?
)
INSERT INTO bridge.users_properties (item_id, user_id) VALUES (?, ?);
"""

_INS_B2_PERSON = """
IF NOT EXISTS (
    SELECT 1 FROM bridge.users_contacts WHERE item_id = ? AND user_id = ?
)
INSERT INTO bridge.users_contacts (item_id, user_id) VALUES (?, ?);
"""


# ---------------------------------------------------------------------------
# Sync functions
# ---------------------------------------------------------------------------

def sync_users(cur: pyodbc.Cursor) -> None:
    print("  Syncing lookup.users...")
    users = fetch_users()
    for u in users:
        cur.execute(
            _UPSERT_USER,
            int(u["id"]),
            u.get("name"),
            u.get("email"),
            u.get("title"),
            1 if u.get("enabled", True)   else 0,
            1 if u.get("is_admin", False) else 0,
            1 if u.get("is_guest", False) else 0,
            u.get("photo_thumb"),
        )
    print(f"    {len(users)} users upserted.")


def sync_board2(cur: pyodbc.Cursor) -> set[int]:
    print("  Syncing core.test_contacts...")
    items = fetch_board_items(BOARD2_ID)
    people_rows: list[tuple[int, int]] = []

    for item in items:
        cv = col_map(item)
        date          = parse_date(cv.get(B2_DATE))
        email, label  = parse_email(cv.get(B2_EMAIL))
        cur.execute(
            _UPSERT_B2,
            int(item["id"]),
            item["group"]["id"], item["group"]["title"],
            item["name"],
            date, email, label,
            item.get("created_at"), item.get("updated_at"),
        )
        for uid in parse_people(cv.get(B2_PERSON)):
            people_rows.append((int(item["id"]), uid))

    for item_id, user_id in people_rows:
        cur.execute(_INS_B2_PERSON, item_id, user_id, item_id, user_id)

    print(f"    {len(items)} items, {len(people_rows)} person rows.")
    return {int(i["id"]) for i in items}


def sync_board1(cur: pyodbc.Cursor, b2_ids: set[int]) -> None:
    print("  Syncing core.test_properties...")
    items = fetch_board_items(BOARD1_ID)
    people_rows:   list[tuple[int, int]] = []
    relation_rows: list[tuple[int, int]] = []

    for item in items:
        cv  = col_map(item)
        loc = parse_location(cv.get(B1_LOCATION))
        cur.execute(
            _UPSERT_B1,
            int(item["id"]),
            item["group"]["id"], item["group"]["title"],
            item["name"],
            loc.get("address"), loc.get("city"), loc.get("country"),
            loc.get("lat"),     loc.get("lng"),  loc.get("place_id"),
            parse_status(cv.get(B1_STATUS)),
            parse_date(cv.get(B1_DATE)),
            item.get("created_at"), item.get("updated_at"),
        )
        for uid in parse_people(cv.get(B1_PERSON)):
            people_rows.append((int(item["id"]), uid))
        for rid in parse_relation(cv.get(B1_RELATION)):
            if rid in b2_ids:
                relation_rows.append((int(item["id"]), rid))

    for item_id, user_id in people_rows:
        cur.execute(_INS_B1_PERSON, item_id, user_id, item_id, user_id)
    for b1_id, b2_id in relation_rows:
        cur.execute(_INS_RELATION, b1_id, b2_id, b1_id, b2_id)

    print(f"    {len(items)} items, {len(people_rows)} person rows, "
          f"{len(relation_rows)} relation rows.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Connecting to RipcoMonday on {SQL_SERVER}...")
    with pyodbc.connect(SQL_CONN_STR, autocommit=False) as conn:
        cur = conn.cursor()
        try:
            sync_users(cur)
            b2_ids = sync_board2(cur)
            sync_board1(cur, b2_ids)
            conn.commit()
            print("Done — all changes committed.")
        except Exception as exc:
            conn.rollback()
            print(f"ERROR: {exc}", file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
