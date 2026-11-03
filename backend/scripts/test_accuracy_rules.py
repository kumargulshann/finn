import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from decimal import Decimal, InvalidOperation

# Test sentences from real transcripts
test_sentences = [
    # False positives that should NOT match revenue:
    ("AI revenue was a standout at 10.5% of our revenue, growing at 29%", "revenue", None),
    ("Our AI services revenue was 8.2% of overall revenue in Q1.", "revenue", None),
    ("And finally, Airtel Money has now achieved meaningful scale with a Q1 revenue of over $400 million growing at", "revenue", None), # segment revenue
    
    # Real revenue:
    ("Our consolidated revenue was Rs.58,500 Crores, growing at about 5.7%", "revenue", ("INR crore", Decimal("58500"))),
    ("Q2 revenues were $5,145 mn, an increase of 1.2% sequentially", "revenue", ("million", Decimal("5145"))),
    
    # Real revenue growth:
    ("Our revenue growth for Q2 was 1.5% YoY and 1.2% sequentially in constant currency terms.", "revenue growth", ("%", Decimal("1.5"))),
    ("Our revenue growth for Q1 was at 2.4% Y-on-Y and 1% Q-on-Q in constant currency terms.", "revenue growth", ("%", Decimal("2.4"))),
    ("Our Q4 revenue growth was 4.1% year-on-year in constant currency", "revenue growth", ("%", Decimal("4.1"))),
    ("Our revenue grew 0.6% sequentially and 1.7% year-on-year in constant currency terms.", "revenue growth", ("%", Decimal("1.7"))),
    
    # False revenue growth:
    ("Revenue growth was below our expectations, while AI first revenue now accounts for 10.5% of our total revenue", "revenue growth", None),
    
    # Operating margin:
    ("Our operating margin guidance remains at 20% to 22%", "operating margin", ("%", Decimal("20"))),
    ("Operating margin was stable at 21%.", "operating margin", ("%", Decimal("21"))),
    ("Q2 operating margins were at 21%, decline of 0.1% sequentially.", "operating margin", ("%", Decimal("21"))),
    ("Our operating margin was 21.1%.", "operating margin", ("%", Decimal("21.1"))),
    
    # PAT:
    ("Profit after tax grew by 20.1% year-on-year to ₹14,843 crore in Q2-2027", "PAT", ("INR crore", Decimal("14843"))),
    ("Profit after tax grew by 15.9% year-on-year to ₹14,805 crore in Q1-2027", "PAT", ("INR crore", Decimal("14805"))),
    ("Profit after tax grew by 8.5% year-on-year to ₹13,702 crore in Q4 2026", "PAT", ("INR crore", Decimal("13702"))),
]

MONETARY_METRICS = {"revenue", "EBITDA", "PAT", "ARPU", "cash flow from operations"}
RATIO_METRICS = {"revenue growth", "operating margin", "EBITDA margin"}

print("Test sentences verification:")
for s, metric, expected in test_sentences:
    print(f"\nText: {s}")
    print(f"Metric: {metric} | Expected: {expected}")

