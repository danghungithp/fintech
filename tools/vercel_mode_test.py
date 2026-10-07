"""Local simulation of the Vercel runtime: import app.py with VERCEL=1.

Data now lives in InfluxDB Cloud (shared by every instance), so this test also
exercises a real read against the bucket configured in .env.
"""
import os
import sys

os.environ["VERCEL"] = "1"

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
sys.path.insert(0, root)

ns = {"__name__": "app", "__file__": "app.py"}
exec(compile(open("app.py", encoding="utf-8").read(), "app.py", "exec"), ns)
app = ns["app"]

client = app.test_client()
health = client.get("/api/health").get_json()
print("health:", health)
assert health["status"] == "ok", "health failed"
assert health["serverless"] is True, "serverless flag missing"
assert health["storage"] == "influxdb-cloud", "storage flag missing"

dash = client.get("/")
print("dashboard:", dash.status_code, "| brand:", "FinViet Pro" in dash.get_data(as_text=True))
assert dash.status_code == 200

settings = client.get("/api/settings")
print("settings:", settings.status_code)
assert settings.status_code == 200, (
    f"settings endpoint failed: {settings.status_code} "
    f"{settings.get_data(as_text=True)[:200]}"
)
assert "equity" in settings.get_json()

print("VERCEL-MODE OK")
