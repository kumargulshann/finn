import re

tail = " was Rs.58,500 Crores, growing at about 5.7%"
monetary_re = re.compile(
    r"(?:(?P<curr>₹|\$|INR|Rs\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn|₹|INR|Rs\.?)?",
    re.I
)
m = monetary_re.search(tail)
print("Search:", m.groups() if m else None)
for match in monetary_re.finditer(tail):
    if match.group("num"):
        print("Finditer:", match.group("curr"), match.group("num"), match.group("unit"))

