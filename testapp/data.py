"""
Sample dataset for testing fiat-lux-agents.
Simulates a sales dataset — simple enough to reason about, rich enough to filter/query/chat.
"""

SAMPLE_DATA = [
    {"id": 1,  "name": "Alice",   "region": "West",  "category": "Electronics", "status": "completed", "amount": 1200, "units": 3,  "month": "Jan"},
    {"id": 2,  "name": "Bob",     "region": "East",  "category": "Clothing",    "status": "pending",   "amount": 340,  "units": 5,  "month": "Jan"},
    {"id": 3,  "name": "Carol",   "region": "West",  "category": "Electronics", "status": "completed", "amount": 890,  "units": 2,  "month": "Feb"},
    {"id": 4,  "name": "Dave",    "region": "North", "category": "Food",        "status": "cancelled", "amount": 150,  "units": 10, "month": "Feb"},
    {"id": 5,  "name": "Eve",     "region": "South", "category": "Electronics", "status": "completed", "amount": 2100, "units": 1,  "month": "Mar"},
    {"id": 6,  "name": "Frank",   "region": "East",  "category": "Clothing",    "status": "completed", "amount": 620,  "units": 8,  "month": "Mar"},
    {"id": 7,  "name": "Grace",   "region": "West",  "category": "Food",        "status": "pending",   "amount": 95,   "units": 15, "month": "Apr"},
    {"id": 8,  "name": "Hank",    "region": "North", "category": "Electronics", "status": "completed", "amount": 1750, "units": 2,  "month": "Apr"},
    {"id": 9,  "name": "Ivy",     "region": "South", "category": "Clothing",    "status": "pending",   "amount": 480,  "units": 6,  "month": "May"},
    {"id": 10, "name": "Jack",    "region": "East",  "category": "Food",        "status": "completed", "amount": 230,  "units": 20, "month": "May"},
    {"id": 11, "name": "Karen",   "region": "West",  "category": "Electronics", "status": "cancelled", "amount": 560,  "units": 1,  "month": "Jun"},
    {"id": 12, "name": "Leo",     "region": "North", "category": "Clothing",    "status": "completed", "amount": 910,  "units": 7,  "month": "Jun"},
    {"id": 13, "name": "Mia",     "region": "South", "category": "Food",        "status": "completed", "amount": 310,  "units": 12, "month": "Jul"},
    {"id": 14, "name": "Ned",     "region": "East",  "category": "Electronics", "status": "pending",   "amount": 1400, "units": 3,  "month": "Jul"},
    {"id": 15, "name": "Olivia",  "region": "West",  "category": "Clothing",    "status": "completed", "amount": 740,  "units": 9,  "month": "Aug"},
]

SCHEMA = """Columns:
- id (int): unique row identifier
- name (str): salesperson name
- region (str): West | East | North | South
- category (str): Electronics | Clothing | Food
- status (str): completed | pending | cancelled
- amount (float): sale amount in dollars
- units (int): number of units sold
- month (str): Jan through Aug
"""

SUMMARY = {
    "total_rows": len(SAMPLE_DATA),
    "columns": ["id", "name", "region", "category", "status", "amount", "units", "month"],
    "categories": ["Electronics", "Clothing", "Food"],
    "regions": ["West", "East", "North", "South"],
    "statuses": ["completed", "pending", "cancelled"],
    "amount_range": [min(r["amount"] for r in SAMPLE_DATA), max(r["amount"] for r in SAMPLE_DATA)],
}
