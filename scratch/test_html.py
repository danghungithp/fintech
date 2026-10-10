import sys
sys.path.append('d:/projects/fintech')
from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['uid'] = 'admin'
    
    resp = client.get('/canslim')
    with open('d:/projects/fintech/scratch/out.html', 'w', encoding='utf-8') as f:
        f.write(resp.get_data(as_text=True))

