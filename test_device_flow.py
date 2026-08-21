import requests
import time

# Wait a moment then poll for token
time.sleep(2)
resp = requests.post('http://localhost:8000/v1/auth/device/token',
    data={'grant_type': 'urn:ietf:params:oauth:grant-type:device_code', 
          'device_code': 'xoWZxORno3SyCp3Gt_t5AE78Sqv5j_Jzm-lugxF0C4g',
          'client_id': 'workflo_cli'},
    timeout=10)
print(f'Device token (authorized): status={resp.status_code}')
if resp.status_code == 200:
    data = resp.json()
    access_token = data.get('access_token', '')
    print(f'Access token: {access_token[:20]}...')
    print(f'Expires in: {data.get("expires_in")}')
else:
    print(f'Error: {resp.text[:300]}')