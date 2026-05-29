# Monday.com → SQL Data Model


Monday.com boards look simple on the surface:

| Board | Columns |
|---|---|
| **Properties** | Name, Status, Date, Location, Person, → Contacts |
| **Contacts** | Name, Email, Date, Person |

But two columns — **Person** and the **board connection** — can each hold
**multiple values per row**. A single property can have 3 assigned users and
link to 5 contacts. You can't store that in one flat table without duplicating
or losing data.

---

## In SQL: 5 Tables

```
monday.com                          SQL (Ripco_Monday_Data)
──────────────────                  ──────────────────────────────────────

                                    ┌─────────────────────┐
                                    │   lookup.users       │
                                    │─────────────────────│
                                    │ 🔑 user_id           │
All 160 monday users ──────────────▶│ name                │
                                    │ email               │
                                    │ title               │
                                    └────────┬────────────┘
                                             │
                              ┌──────────────┴──────────────┐
                              │                             │
                    ┌─────────▼───────────┐   ┌────────────▼────────────┐
                    │ bridge.users_       │   │ bridge.users_           │
                    │ properties          │   │ contacts                │
                    │─────────────────────│   │─────────────────────────│
                    │ 🔑 id               │   │ 🔑 id                   │
                    │ item_id  ──┐        │   │ item_id  ──┐            │
                    │ user_id  ──┘        │   │ user_id  ──┘            │
                    └─────────┬───────────┘   └────────────┬────────────┘
                              │                             │
                    ┌─────────▼───────────┐   ┌────────────▼────────────┐
                    │ core.test_          │   │ core.test_              │
                    │ properties          │   │ contacts                │
                    │─────────────────────│   │─────────────────────────│
                    │ 🔑 item_id          │   │ 🔑 item_id              │
Board 1 ───────────▶│ name               │   │ name        ◀─── Board 2│
                    │ status             │   │ email                   │
                    │ date               │   │ date                    │
                    │ location           │   └─────────────────────────┘
                    └─────────┬───────────┘               ▲
                              │                           │
                    ┌─────────▼───────────────────────────┴──┐
                    │       bridge.properties_contacts        │
                    │────────────────────────────────────────│
                    │ 🔑 id                                   │
  Board connection ▶│ property_item_id                       │
  column            │ contact_item_id                        │
                    └─────────────────────────────────────────┘
```

---

## Why Each Table Exists

| Table | Schema | What It Stores | Why It Can't Be in the Main Table |
|---|---|---|---|
| `users` | `lookup` | Every Monday user in our account | Shared across all boards — store once, reference everywhere |
| `test_properties` | `core` | One row per property item | Core board data — straightforward 1-to-1 |
| `test_contacts` | `core` | One row per contact item | Core board data — straightforward 1-to-1 |
| `properties_contacts` | `bridge` | Links properties to contacts | One property can connect to **many** contacts |
| `users_properties` | `bridge` | Links users to properties | One property can be assigned to **many** users |
| `users_contacts` | `bridge` | Links users to contacts | One contact can be assigned to **many** users |

---

## A Real Example

Say we have this in Monday:

> **Property:** 150 E 58th Street
> - Assigned to: William Parra, Andie Miller
> - Linked contacts: John Developer, Joe Landlord

In SQL that becomes **5 rows across 4 tables**:

```
core.test_properties        → 1 row  (the property itself)
core.test_contacts          → 2 rows (John Developer, Joe Landlord)
bridge.users_properties     → 2 rows (William → property, Andie → property)
bridge.properties_contacts  → 2 rows (property → John, property → Joe)
```

---

## For Reporting (Power BI)

The 5-table model is the **engine under the hood**.
Analysts never touch it directly.

Instead, we create **Views** — pre-joined flat tables that look like this:

| property_name | status | assigned_to | contact_name | contact_email |
|---|---|---|---|---|
| 150 E 58th Street | Working on it | William Parra | John Developer | john@dev.com |
| 150 E 58th Street | Working on it | Andie Miller | John Developer | john@dev.com |
| 27 Hattertown Road | Done | William Parra | Joe Landlord | joe@land.com |

One view. Drag and drop in Power BI. No SQL required.
