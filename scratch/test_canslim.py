import sys
sys.path.append('d:/projects/fintech')
from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['uid'] = 'admin'
    
    resp = client.post('/api/canslim/calc', json={'symbol': 'FPT'})
    print("Status:", resp.status_code)
    try:
        print("Data keys:", resp.get_json().keys() if resp.get_json() else "None")
    except Exception as e:
        print("Failed to decode JSON", e)

