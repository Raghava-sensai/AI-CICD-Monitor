import requests

with open("dummy.zip", "wb") as f:
    f.write(b"PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")

url = "http://127.0.0.1:5000/api/v1/deployment/upload"
with open("dummy.zip", "rb") as f:
    res = requests.post(url, files={"file": ("dummy.zip", f)})

print("Status Code:", res.status_code)
print("Response:", res.text)
