# CRUD_Marketplace

Layered architecture: Services -> Interfaces -> Implementation, plus View.

## Run the interface (Python 3.13 + Flask)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python View/MainViews/PY/app.py
```

Open http://127.0.0.1:5000

Before running, set your API Gateway invoke URL in `View/MainViews/Utils/api_client.py` (`API_URL`).
Optional environment variables: `API_URL`, `SECRET_KEY`, `FLASK_DEBUG=1`.
