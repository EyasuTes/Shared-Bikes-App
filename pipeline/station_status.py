import json
from urllib.request import Request, urlopen

URL = "https://gbfs.lyft.com/gbfs/2.3/dca-cabi/en/station_status.json"

request = Request(
    URL,
    headers={
        "Accept": "application/json",
        "User-Agent": "bike-project/1.0",
    },
)

with urlopen(request, timeout=15) as response:
    data = json.load(response)

stations = data["data"]["stations"]

# Calculate count of stations with zero bikes available
zero_bikes_count = sum(1 for station in stations if station.get("num_bikes_available") == 0)

print("Total number of stations:", len(stations))
print("Stations with zero bikes available:", zero_bikes_count)
print("=" * 40)

# Print individual station details
for station in stations:
    if station.get("num_bikes_available") == 0:
        print("Station ID:", station["station_id"])
        print("Bikes available:", station["num_bikes_available"])
        print("Docks available:", station["num_docks_available"])
        print("Last reported:", station["last_reported"])
        print("-" * 40)