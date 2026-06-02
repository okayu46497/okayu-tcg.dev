import requests
import re

url = 'https://dm.takaratomy.co.jp/card/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest'
}

response = requests.post(url, data={'pagenum': '1'}, headers=headers, timeout=10)
print(f"Response Status: {response.status_code}")

# <span class="fontTbu" id ="total_count">XXXX</span> を抽出
total_match = re.search(r'id\s*=\s*[\'"]total_count[\'"]>(\d+)</span>', response.text)
if total_match:
    print(f"Total Count: {total_match.group(1)}")
else:
    # 代替の正規表現
    total_match2 = re.search(r'class="fontTbu"[^>]*>(\d+)</span>', response.text)
    if total_match2:
        print(f"Total Count (Alternative): {total_match2.group(1)}")
    else:
        print("Total count element not found in HTML. Printing first 1000 characters:")
        print(response.text[:1000])

# 1ページあたりの件数（<li> の数をカウント）
card_lis = re.findall(r'<li><a href=\'/card/detail/\?id=', response.text)
print(f"Number of cards on Page 1: {len(card_lis)}")
