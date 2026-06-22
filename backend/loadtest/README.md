# Load testing

See [locustfile.py](./locustfile.py).

```bash
pip install -r backend/loadtest/requirements.txt
cd backend
locust -f loadtest/locustfile.py --host http://127.0.0.1:8000
```

Open http://localhost:8089 for the Locust UI.

For authenticated project-list probes, export a JWT:

```bash
export LOADTEST_JWT=<access_token>
```
