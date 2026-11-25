# BroShare REST API

All paths below are relative to `/api/`. Send `Authorization: Bearer <access>` on private requests and `X-Flat-ID: <id>` to select a workspace. Amounts are integer paise. Dates use ISO format. Lists support `page` and `page_size` up to 100.

| Endpoint | Operations and request fields |
| --- | --- |
| `auth/register/` | POST username, password, optional email |
| `auth/login/` | POST username, password. Returns access and refresh |
| `auth/refresh/` | POST refresh. Returns rotated tokens |
| `auth/logout/` | POST refresh. Blacklists refresh token |
| `auth/me/` | GET profile and memberships. PATCH email |
| `flats/` | POST name. Supply invite to join a flat |
| `workspace/` | GET name and lead-only invite. Lead PATCH name or POST to rotate invite |
| `sync-check/` | GET workspace update timestamp |
| `roommates/` | GET directory. Lead POST name, upi, role. PATCH details or DELETE to archive by ID |
| `roommates/{id}/restore/` | Lead POST restores a member |
| `roommates/guest/` | POST name, optional upi and trip ID |
| `billing-cycle/` | GET cycles. Lead POST month formatted YYYY-MM |
| `billing-cycle/settle-month/` | Lead POST cycle ID and rollover boolean |
| `billing-cycle/reopen/` | Lead POST cycle ID |
| `summary/` | GET with cycle ID, cycle=all, or trip ID |
| `expenses/` | GET list, filter by cycle, trip, payer, category, scope or search. POST expense and split rows |
| `expenses/{id}/` | PATCH expense or DELETE to archive. Ledger is fixed after creation |
| `settlements/` | GET entries. POST payer, receiver, paise, cycle or trip, request_key UUID, method, optional reference and notes |
| `settlements/{id}/confirm/` | POST method, reference, notes to confirm pending payment |
| `settlements/{id}/reverse/` | POST or DELETE at detail endpoint to reverse |
| `payment-qr/` | POST receiver and paise. Returns UPI URL and QR vector geometry |
| `trips/` | GET or POST name, destination, start, end, budget, status, participants array. PATCH or lead DELETE by ID |
| `chores/` | GET or POST title, assigned, due, points and frequency. PATCH or DELETE by ID |
| `chores/{id}/complete/` | POST current due date. Rotates the assignee and records history |
| `chores/{id}/swap/` | POST member ID |
| `maintenance/` | GET or POST title, notes, technician, priority, status, estimated, actual. PATCH by ID |
| `maintenance/{id}/convert-to-expense/` | POST payer ID. Safe to retry |
| `reminders/` | GET personalized reminders or POST title and notes. PATCH read or DELETE to dismiss by ID |
| `reports/{kind}/` | GET monthly, categories, trips, contributions, or settlements |
| `export/` | Lead GET workspace JSON |
| `import/` | Lead POST backup object and confirmed=true. Creates a new workspace |

Example expense payload:

```json
{
  "title": "Electricity",
  "paise": 125050,
  "category": "Electricity",
  "payer": 1,
  "cycle": 1,
  "date": "2026-11-24",
  "split_type": "PERCENT",
  "splits": [
    {"member": 1, "value": "60"},
    {"member": 2, "value": "40"}
  ]
}
```

For `EXACT`, split values are rupees with up to two decimals. `PERCENT` values sum to 100. `SHARES` uses relative weights. `EQUAL` omits values or uses 1. Household recurrence definitions use `WEEKLY`, `BIWEEKLY`, or `MONTHLY`. API validation returns standard DRF field errors or a `detail` message.

