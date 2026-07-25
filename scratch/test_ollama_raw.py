import urllib.request
import json

base_url = "http://localhost:50050"
api_url = f"{base_url}/api/chat"
model = "qwen3:14b"

payload = {
    "model": model,
    "messages": [
        {"role": "user", "content": "Say hello"}
    ],
    "stream": False,
    "format": "json"
}

print(f"Sending request to {api_url}...")
request = urllib.request.Request(
    api_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(request, timeout=10) as response:
        status_code = response.getcode()
        body = response.read().decode("utf-8")
        print(f"Status Code: {status_code}")
        print("Response Body:")
        print(body[:1000])
except Exception as e:
    print(f"Error calling Ollama: {e}")
