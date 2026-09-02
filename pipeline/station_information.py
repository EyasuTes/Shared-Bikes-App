import json
from urllib.request import Request, urlopen

URL = "https://gbfs.lyft.com/gbfs/2.3/dca-cabi/en/station_information.json"

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

print("Number of stations:", len(stations))
print()

for station in stations[:10]:
    print("Station ID:", station["station_id"])
    print("Name:", station["name"])
    print("Latitude:", station["lat"])
    print("Longitude:", station["lon"])
    print("Capacity:", station["capacity"])
    print("-" * 40)