"""
Shared database and parsing logic for Monday.com -> Ripco_Monday_Data sync.
Imported by both sync_monday.py (full backfill) and function_app.py (webhooks).
"""

from __future__ import annotations

import json
import os

import pyodbc

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection() -> pyodbc.Connection:
    _uid = os.environ.get("SQL_UID")
    _pwd = os.environ.get("SQL_PWD")
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={os.environ['SQL_SERVER']};DATABASE=Ripco_Monday_Data;"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        + (f"UID={_uid};PWD={_pwd};" if _uid else "Trusted_Connection=yes;")
    )
    return pyodbc.connect(conn_str, autocommit=False)

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


def _str(val) -> str | None:
    if val is None:
        return None
    return str(val) if not isinstance(val, str) else val


def parse_people(raw) -> list[int]:
    v = _j(raw)
    if not v:
        return []
    if isinstance(v, list):
        return [int(p["id"]) for p in v if p.get("kind") == "person"]
    return [int(p["id"]) for p in v.get("personsAndTeams", []) if p.get("kind") == "person"]


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


def parse_status(raw) -> str | None:
    v = _j(raw)
    return v.get("label") if v else None


def parse_date(raw) -> str | None:
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


def parse_email(raw) -> tuple[str | None, str | None]:
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
# SQL — upserts
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

_UPSERT_PROPERTY = """
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

_UPSERT_CONTACT = """
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

_INS_PROP_PERSON = """
IF NOT EXISTS (
    SELECT 1 FROM bridge.users_properties WHERE item_id = ? AND user_id = ?
)
INSERT INTO bridge.users_properties (item_id, user_id) VALUES (?, ?);
"""

_INS_CONT_PERSON = """
IF NOT EXISTS (
    SELECT 1 FROM bridge.users_contacts WHERE item_id = ? AND user_id = ?
)
INSERT INTO bridge.users_contacts (item_id, user_id) VALUES (?, ?);
"""

# ---------------------------------------------------------------------------
# SQL — deletes
# ---------------------------------------------------------------------------

_DEL_PROPERTY = """
DELETE FROM bridge.users_properties      WHERE item_id          = ?;
DELETE FROM bridge.properties_contacts   WHERE property_item_id = ?;
DELETE FROM core.test_properties         WHERE item_id          = ?;
"""

_DEL_CONTACT = """
DELETE FROM bridge.users_contacts        WHERE item_id         = ?;
DELETE FROM bridge.properties_contacts   WHERE contact_item_id = ?;
DELETE FROM core.test_contacts           WHERE item_id         = ?;
"""

# ---------------------------------------------------------------------------
# Public write helpers
# ---------------------------------------------------------------------------

# Monday column IDs
B1_PERSON   = "person"
B1_LOCATION = "location_mm3spvjs"
B1_STATUS   = "status"
B1_DATE     = "date4"
B1_RELATION = "board_relation_mm3tq3kq"

B2_PERSON = "person"
B2_DATE   = "date4"
B2_EMAIL  = "email_mm3sbzqz"


def upsert_user(cur: pyodbc.Cursor, u: dict) -> None:
    cur.execute(
        _UPSERT_USER,
        int(u["id"]), u.get("name"), u.get("email"), u.get("title"),
        1 if u.get("enabled", True)   else 0,
        1 if u.get("is_admin", False) else 0,
        1 if u.get("is_guest", False) else 0,
        u.get("photo_thumb"),
    )


def upsert_property(cur: pyodbc.Cursor, item: dict, contact_ids: set[int]) -> None:
    cv  = col_map(item)
    loc = parse_location(cv.get(B1_LOCATION))
    cur.execute(
        _UPSERT_PROPERTY,
        int(item["id"]),
        item["group"]["id"], item["group"]["title"],
        item["name"],
        loc.get("address"), loc.get("city"), loc.get("country"),
        loc.get("lat"),     loc.get("lng"),  loc.get("place_id"),
        parse_status(cv.get(B1_STATUS)),
        parse_date(cv.get(B1_DATE)),
        item.get("created_at"), item.get("updated_at"),
    )
    # Refresh bridge rows: delete then re-insert so removals are captured
    cur.execute("DELETE FROM bridge.users_properties    WHERE item_id          = ?", int(item["id"]))
    cur.execute("DELETE FROM bridge.properties_contacts WHERE property_item_id = ?", int(item["id"]))
    for uid in parse_people(cv.get(B1_PERSON)):
        cur.execute(_INS_PROP_PERSON, int(item["id"]), uid, int(item["id"]), uid)
    for rid in parse_relation(cv.get(B1_RELATION)):
        if rid in contact_ids:
            cur.execute(_INS_RELATION, int(item["id"]), rid, int(item["id"]), rid)


def upsert_contact(cur: pyodbc.Cursor, item: dict) -> None:
    cv = col_map(item)
    date         = parse_date(cv.get(B2_DATE))
    email, label = parse_email(cv.get(B2_EMAIL))
    cur.execute(
        _UPSERT_CONTACT,
        int(item["id"]),
        item["group"]["id"], item["group"]["title"],
        item["name"],
        date, email, label,
        item.get("created_at"), item.get("updated_at"),
    )
    cur.execute("DELETE FROM bridge.users_contacts WHERE item_id = ?", int(item["id"]))
    for uid in parse_people(cv.get(B2_PERSON)):
        cur.execute(_INS_CONT_PERSON, int(item["id"]), uid, int(item["id"]), uid)


def delete_property(cur: pyodbc.Cursor, item_id: int) -> None:
    cur.execute("DELETE FROM bridge.users_properties    WHERE item_id          = ?", item_id)
    cur.execute("DELETE FROM bridge.properties_contacts WHERE property_item_id = ?", item_id)
    cur.execute("DELETE FROM core.test_properties       WHERE item_id          = ?", item_id)


def delete_contact(cur: pyodbc.Cursor, item_id: int) -> None:
    cur.execute("DELETE FROM bridge.users_contacts      WHERE item_id         = ?", item_id)
    cur.execute("DELETE FROM bridge.properties_contacts WHERE contact_item_id = ?", item_id)
    cur.execute("DELETE FROM core.test_contacts         WHERE item_id         = ?", item_id)
