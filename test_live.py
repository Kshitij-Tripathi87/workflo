import requests
import time

# First, get a demo token
resp = requests.post('http://localhost:8000/v1/auth/demo-token', timeout=5)
print(f'Demo token: status={resp.status_code}')
if resp.status_code == 200:
    key = resp.json().get('api_key', '')
    print(f'Key: {key[:20]}...')
    
    # Try a run via the API
    headers = {'X-API-Key': key}
    run_resp = requests.post(
        'http://localhost:8000/v1/runs',
        json={
            'repo_url': 'https://github.com/pallets/click.git',
            'probe_groups': ['test', 'security']
        },
        headers=headers,
        timeout=10
    )
    print(f'Run submit: status={run_resp.status_code}')
    print(f'Run response: {run_resp.text[:500]}')
else:
    print(f'Demo token failed: {resp.text[:200]}')