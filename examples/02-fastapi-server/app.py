"""
FastAPI example for pybox.

Demonstrates that a web server runs normally inside the sandbox.
The /escape endpoint intentionally tries to write outside the working
directory so the PermissionError can be observed in the response.
"""

import pathlib
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="pybox fastapi example")

LOGS = pathlib.Path("logs")
LOGS.mkdir(exist_ok=True)


@app.get("/")
def health():
    return {"status": "ok", "sandbox": "pybox"}


@app.get("/items/{item_id}")
def get_item(item_id: int):
    return {"id": item_id, "name": f"Widget {item_id}", "price": item_id * 9.99}


class LogRequest(BaseModel):
    message: str


@app.post("/log")
def write_log(req: LogRequest):
    """Write a log entry inside the working directory — allowed by the sandbox."""
    entry = f"{datetime.utcnow().isoformat()} {req.message}\n"
    with open(LOGS / "requests.log", "a") as f:
        f.write(entry)
    return {"logged": req.message, "file": str(LOGS / "requests.log")}


@app.post("/escape")
def escape():
    """
    Attempt to write outside the working directory.

    The sandbox blocks this at the OS level. The PermissionError propagates
    up and is returned as a 500 response — the server itself keeps running.
    """
    try:
        with open("/tmp/escaped.txt", "w") as f:
            f.write("this should not be written")
        return {"result": "ERROR: write succeeded — sandbox did not block it"}
    except PermissionError as e:
        return JSONResponse(
            status_code=500,
            content={"error": "PermissionError", "detail": str(e)},
        )
