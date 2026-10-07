"""Entry point: python app.py"""
from fintech import create_app
from fintech.config import DEBUG, HOST, PORT

app = create_app()

if __name__ == "__main__":
    print(f"* FinViet Pro -* running at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
