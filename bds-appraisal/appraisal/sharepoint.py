"""SharePoint document library storage through Microsoft Graph.

Library layout (under `base_folder`):
    Incoming/                         proposals waiting for appraisal
    Appraised/<YYYY>/<name>_<stamp>/  original file + report.xlsx + report.html + appraisal.json
    Register/appraisal_register.csv   one row per saved appraisal

Authentication is app-only (client credentials) with an Entra ID app
registration. Grant it Sites.Selected and give write access to this one site
(recommended) or Sites.ReadWrite.All.
"""
from __future__ import annotations

import csv
import io
import time
from urllib.parse import quote

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024
CHUNK = 5 * 320 * 1024  # upload sessions need multiples of 320 KiB


class SharePointError(RuntimeError):
    pass


class SharePointClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 hostname: str, site_path: str, drive_name: str = "Documents",
                 base_folder: str = "Livelihood Appraisals"):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.hostname = hostname
        self.site_path = site_path.strip("/")
        self.drive_name = drive_name
        self.base = base_folder.strip("/")
        self._token: str | None = None
        self._token_exp = 0.0
        self._site_id: str | None = None
        self._drive_id: str | None = None

    @classmethod
    def from_secrets(cls, sec) -> "SharePointClient":
        return cls(sec["tenant_id"], sec["client_id"], sec["client_secret"], sec["hostname"],
                   sec["site_path"], sec.get("drive_name", "Documents"),
                   sec.get("base_folder", "Livelihood Appraisals"))

    # ------------------------------------------------------------ plumbing
    def _auth(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        import msal
        app = msal.ConfidentialClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret)
        res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in res:
            raise SharePointError(f"Sign-in to Microsoft Graph failed: {res.get('error_description', res)}")
        self._token = res["access_token"]
        self._token_exp = time.time() + int(res.get("expires_in", 3600))
        return self._token

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._auth()}"
        r = requests.request(method, url if url.startswith("http") else GRAPH + url,
                             headers=headers, timeout=60, **kw)
        if r.status_code >= 400:
            raise SharePointError(f"Graph {method} {url} failed ({r.status_code}): {r.text[:300]}")
        return r

    @property
    def site_id(self) -> str:
        if not self._site_id:
            self._site_id = self._req("GET", f"/sites/{self.hostname}:/{self.site_path}").json()["id"]
        return self._site_id

    @property
    def drive_id(self) -> str:
        if not self._drive_id:
            drives = self._req("GET", f"/sites/{self.site_id}/drives").json()["value"]
            for d in drives:
                if d["name"] in (self.drive_name, "Shared Documents") or d.get("webUrl", "").endswith(quote(self.drive_name)):
                    self._drive_id = d["id"]
                    break
            else:
                raise SharePointError(f"Library '{self.drive_name}' not found. Available: "
                                      + ", ".join(d["name"] for d in drives))
        return self._drive_id

    def _path(self, rel: str) -> str:
        full = f"{self.base}/{rel.strip('/')}" if self.base else rel.strip("/")
        return quote(full)

    # ---------------------------------------------------------------- api
    def test(self) -> str:
        return self._req("GET", f"/sites/{self.site_id}").json().get("webUrl", "")

    def upload(self, rel_path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        if len(data) <= SIMPLE_UPLOAD_LIMIT:
            return self._req("PUT", f"/drives/{self.drive_id}/root:/{self._path(rel_path)}:/content",
                             data=data, headers={"Content-Type": content_type}).json()
        sess = self._req("POST", f"/drives/{self.drive_id}/root:/{self._path(rel_path)}:/createUploadSession",
                         json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}).json()
        url, total, res = sess["uploadUrl"], len(data), None
        for start in range(0, total, CHUNK):
            chunk = data[start:start + CHUNK]
            end = start + len(chunk) - 1
            r = requests.put(url, data=chunk, timeout=120, headers={
                "Content-Length": str(len(chunk)), "Content-Range": f"bytes {start}-{end}/{total}"})
            if r.status_code >= 400:
                raise SharePointError(f"Chunk upload failed ({r.status_code}): {r.text[:200]}")
            res = r.json()
        return res or {}

    def list_folder(self, rel_path: str) -> list[dict]:
        try:
            items = self._req("GET", f"/drives/{self.drive_id}/root:/{self._path(rel_path)}:/children"
                                     "?$select=id,name,size,lastModifiedDateTime,webUrl,file").json()["value"]
        except SharePointError as exc:
            if "404" in str(exc):
                return []
            raise
        return [i for i in items if "file" in i]

    def download(self, item_id: str) -> bytes:
        return self._req("GET", f"/drives/{self.drive_id}/items/{item_id}/content").content

    def download_path(self, rel_path: str) -> bytes | None:
        try:
            return self._req("GET", f"/drives/{self.drive_id}/root:/{self._path(rel_path)}:/content").content
        except SharePointError as exc:
            if "404" in str(exc):
                return None
            raise

    def append_register(self, row: dict, rel_path: str = "Register/appraisal_register.csv") -> None:
        existing = self.download_path(rel_path)
        rows: list[dict] = []
        fields = list(row.keys())
        if existing:
            reader = csv.DictReader(io.StringIO(existing.decode("utf-8-sig")))
            rows = list(reader)
            fields = list(dict.fromkeys((reader.fieldnames or []) + fields))
        rows.append(row)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
        self.upload(rel_path, buf.getvalue().encode("utf-8-sig"), "text/csv")

    def read_register(self, rel_path: str = "Register/appraisal_register.csv") -> list[dict]:
        data = self.download_path(rel_path)
        if not data:
            return []
        return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
