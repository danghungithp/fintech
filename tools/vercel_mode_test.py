"""Local simulation of the Vercel runtime: import app.py with VERCEL=1."""
import os
import shutil
import sys

os.environ["VERCEL"] = "1"
os.environ["FINTECH_DATA_DIR"] = ".vercel-data-test"

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
sys.path.insert(0, root)

expected_db = os.path.join(root, ".vercel-data-test", "fintech.db")

ns = {"__name__": "app", "__file__": "app.py"}
exec(compile(open("app.py", encoding="utf-8").read(), "app.py", "exec"), ns)
app = ns["app"]

client = app.test_client()
health = client.get("/api/health").get_json()
print("health:", health)
assert health["status"] == "ok", "health failed"
assert health["serverless"] is True, "serverless flag missing"
assert health["storage"] == "ephemeral", "storage flag missing"

dash = client.get("/")
print("dashboard:", dash.status_code, "| brand:", "FinViet Pro" in dash.get_data(as_text=True))
assert dash.status_code == 200

settings = client.get("/api/settings").get_json()
print("settings loaded:", "equity" in settings)

db_existed = os.path.exists(expected_db)
print("db created in override dir:", db_existed)
assert db_existed

shutil.rmtree(os.path.join(root, ".vercel-data-test"), ignore_errors=True)
print("VERCEL-MODE OK")
