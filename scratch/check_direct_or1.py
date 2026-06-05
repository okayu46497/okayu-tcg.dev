import requests
import re

def check_direct():
    url = "https://dm.takaratomy.co.jp/card/detail/?id=dm22rp1-or1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Fetching direct page for dm22rp1-or1...")
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        html = resp.text
        name_match = re.search(r"class=['\"]card-name['\"]>([^<]+?)<", html)
        name = name_match.group(1).strip() if name_match else "Not found"
        print(f"Status: {resp.status_code}")
        print(f"Card Name: {name}")
    else:
        print(f"Failed (status={resp.status_code})")

if __name__ == "__main__":
    check_direct()
