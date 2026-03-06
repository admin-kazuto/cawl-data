"""Quick test for ScrapBot API"""
import requests
import json

BASE = "http://localhost:8000"

# 1. Root
print("=" * 50)
print("TEST 1: Root endpoint")
r = requests.get(f"{BASE}/")
print(f"Status: {r.status_code}")
print(f"Response: {r.json()['name']} v{r.json()['version']}")

# 2. Health
print("\n" + "=" * 50)
print("TEST 2: Health check")
r = requests.get(f"{BASE}/health")
print(f"Status: {r.status_code} -> {r.json()}")

# 3. Scrape
print("\n" + "=" * 50)
print("TEST 3: POST /api/scrape (gowell.vn)")
r = requests.post(f"{BASE}/api/scrape", json={
    "url": "https://gowell.vn",
    "max_depth": 1,
    "max_pages": 5
}, timeout=60)
data = r.json()
print(f"Status: {data['status']}")
print(f"Domain: {data['domain']}")
print(f"Pages crawled: {data['pages_crawled']}")
for p in data.get('pages', [])[:3]:
    print(f"  - {p['url'][:60]}: {p['title'][:40]}")

# 4. Classify (if pages exist)
if data.get('pages'):
    print("\n" + "=" * 50)
    print("TEST 4: POST /api/classify")
    pages_meta = [{
        'url': p['url'],
        'title': p['title'],
        'meta_description': p.get('meta_description', ''),
        'structured': p.get('structured', {})
    } for p in data['pages'][:3]]
    
    r2 = requests.post(f"{BASE}/api/classify", json={
        "pages": pages_meta
    }, timeout=60)
    cls_data = r2.json()
    print(f"Status: {cls_data['status']}")
    print(f"Total: {cls_data['total_pages']}")
    for res in cls_data.get('results', []):
        print(f"  - [{res['category']}] {res['product_name'][:40]}")

print("\n" + "=" * 50)
print("ALL TESTS DONE!")
