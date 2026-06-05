import requests
import re

def test_crawl():
    url = "https://dm.takaratomy.co.jp/card/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://dm.takaratomy.co.jp/card/"
    }
    
    data = {
        "pagenum": "1",
        "keyword": "アビスベル",
        "keyword_type[]": "card_name"
    }
    
    print("Querying official DM card search for 'アビスベル'...")
    resp = requests.post(url, data=data, headers=headers)
    if resp.status_code == 200:
        html = resp.text
        # Find all detail links: href='/card/detail/?id=...'
        found_ids = re.findall(r"href=['\"]/card/detail/\?id=([^'\"]+?)['\"]", html)
        print(f"Found {len(found_ids)} card IDs in page 1:")
        for cid in found_ids:
            print(f"  ID: {cid}")
            
        # Let's see if we can find card names in the html fragment
        # The cards are inside some list or grid. Let's print matches of card names
        names = re.findall(r"class=['\"]card-name['\"]>([^<]+?)<", html)
        print(f"Found {len(names)} names in page 1:")
        for n in names:
            print(f"  Name: {n.strip()}")
    else:
        print(f"Failed to fetch official search (status={resp.status_code}): {resp.text}")

if __name__ == "__main__":
    test_crawl()
