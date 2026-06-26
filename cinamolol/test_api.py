from curl_cffi import requests

url = "https://api.arsha.io/v1/kr/item?id=7210"

# impersonate="chrome110" 옵션이 핵심입니다. 크롬 브라우저의 네트워크 지문을 완벽 복제합니다.
response = requests.get(url, impersonate="chrome110")
print(response.json())