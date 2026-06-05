import requests
import re
import time

def test_crawl_jashin():
    url = "https://dm.takaratomy.co.jp/card/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://dm.takaratomy.co.jp/card/"
    }
    
    unique_ids = set()
    page = 1
    
    while True:
        print(f"Querying page {page} for 'ジャシン'...")
        data = {
            "pagenum": str(page),
            "keyword": "ジャシン",
            "keyword_type[]": "card_name"
        }
        resp = requests.post(url, data=data, headers=headers)
        if resp.status_code != 200:
            print("Failed to fetch.")
            break
            
        found_ids = re.findall(r"href=['\"]/card/detail/\?id=([^'\"]+?)['\"]", resp.text)
        if not found_ids:
            print("No more card IDs found.")
            break
            
        page_unique = set(found_ids)
        new_ids = page_unique - unique_ids
        print(f"Page {page}: Found {len(page_unique)} IDs ({len(new_ids)} new)")
        for cid in page_unique:
            unique_ids.add(cid)
            
        page += 1
        time.sleep(1.0)
        
    print(f"\nTotal unique card IDs found for 'ジャシン': {len(unique_ids)}")
    for cid in sorted(unique_ids):
        print(f"  - {cid}")

if __name__ == "__main__":
    test_crawl_jashin()
