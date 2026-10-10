import sys
import json
sys.path.append('d:/projects/fintech')
from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 'test'
    
    resp = client.get('/api/analyze?symbol=VPB')
    data = resp.get_json()
    print("Keys in data:", data.keys() if data else "None")

