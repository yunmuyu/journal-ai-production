import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
request_path, result_path = map(Path, sys.argv[1:3])
key = os.environ.get('TYPESAFE_API_KEY')
if not key:
    raise SystemExit('TypeSafe credential unavailable')
payload = request_path.read_bytes()
start = time.monotonic()
request = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=payload, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    record = {'ok': True, 'response': result, 'durationMs': round((time.monotonic()-start)*1000)}
except urllib.error.HTTPError as error:
    record = {'ok': False, 'httpStatus': error.code, 'error': 'TypeSafe HTTP request failed', 'durationMs': round((time.monotonic()-start)*1000)}
except (urllib.error.URLError, TimeoutError):
    record = {'ok': False, 'error': 'TypeSafe network failure or timeout', 'durationMs': round((time.monotonic()-start)*1000)}
result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
if not record['ok']:
    raise SystemExit(record['error'])
