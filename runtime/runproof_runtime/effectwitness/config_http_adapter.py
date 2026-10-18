"""Fixed loopback HTTP adapters for the RPF-51 controlled config-center run."""
from __future__ import annotations

import http.client
import re
import time
from urllib.parse import quote

from .config_http_contracts import FrozenContracts, strict_json


class AdapterRejected(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise AdapterRejected(code)


_CREDENTIAL = re.compile(r"[A-Za-z0-9._~-]{24,128}\Z")


class _BoundedHttpClient:
    def __init__(self, contracts: FrozenContracts, observations: list[dict] | None = None):
        contracts.validate()
        self.execution = contracts.execution
        self.effect = contracts.effect
        self.http = self.execution["http"]
        self.observations = observations if observations is not None else []
        self.max_requests = self.execution["budgets"]["http_requests"]

    def request(self, kind: str, method: str, path: str, *, request=None,
                credential: str | None = None) -> dict:
        if kind not in ("initial_current", "initial_history", "unauthorized_write",
                        "after_unauthorized_current", "after_unauthorized_history", "create_v1",
                        "update_v2", "stale_update", "final_current", "final_history", "final_list"):
            raise AdapterRejected("REQUEST_KIND_NOT_ALLOWLISTED")
        if len(self.observations) >= self.max_requests:
            raise AdapterRejected("HTTP_REQUEST_BUDGET_EXHAUSTED")
        allowed = {
            "GET": {"/api/configs/" + quote(self.effect["key"], safe="") +
                    "?app=" + quote(self.effect["app"], safe="") + "&env=" + quote(self.effect["env"], safe=""),
                    "/api/configs/history?app=" + quote(self.effect["app"], safe="") +
                    "&env=" + quote(self.effect["env"], safe="") + "&key=" +
                    quote(self.effect["key"], safe="") + "&limit=50",
                    "/api/configs?app=" + quote(self.effect["app"], safe="") +
                    "&env=" + quote(self.effect["env"], safe="")},
            "POST": {"/api/configs"},
        }
        if method not in allowed or path not in allowed[method]:
            raise AdapterRejected("HTTP_PATH_OR_METHOD_NOT_ALLOWLISTED")
        app, env, key = (quote(self.effect[name], safe="") for name in ("app", "env", "key"))
        current = f"/api/configs/{key}?app={app}&env={env}"
        history = f"/api/configs/history?app={app}&env={env}&key={key}&limit=50"
        listed = f"/api/configs?app={app}&env={env}"
        expected = {
            "initial_current": ("GET", current), "initial_history": ("GET", history),
            "unauthorized_write": ("POST", "/api/configs"),
            "after_unauthorized_current": ("GET", current),
            "after_unauthorized_history": ("GET", history),
            "create_v1": ("POST", "/api/configs"), "update_v2": ("POST", "/api/configs"),
            "stale_update": ("POST", "/api/configs"), "final_current": ("GET", current),
            "final_history": ("GET", history), "final_list": ("GET", listed),
        }[kind]
        if (method, path) != expected:
            raise AdapterRejected("HTTP_KIND_PATH_MISMATCH")
        if method == "GET" and request is not None:
            raise AdapterRejected("GET_BODY_FORBIDDEN")
        if method == "POST" and type(request) is not dict:
            raise AdapterRejected("POST_BODY_REQUIRED")

        seq = len(self.observations) + 1
        started = time.monotonic()
        observation = {"seq": seq, "kind": kind, "method": method, "path": path,
                      "request": request, "status": None, "content_type": None, "etag": None,
                      "trace_id": None, "response": None, "response_body_sha256": None,
                      "elapsed_ms": 0, "transport_error": None}
        headers = {"Accept": "application/json"}
        body = None
        if method == "POST":
            from .config_http_contracts import canonical
            body = canonical(request)
            headers["Content-Type"] = "application/json"
            if credential is not None:
                headers[self.http["auth_header"]] = credential
        connection = None
        try:
            # Host is deliberately a literal. The contract's port is the only variable destination.
            connection = http.client.HTTPConnection("127.0.0.1", self.http["port"],
                                                    timeout=self.http["timeout_seconds"])
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            observation["status"] = response.status
            content_type = response.getheader("Content-Type")
            observation["content_type"] = content_type.lower() if isinstance(content_type, str) else None
            etag = response.getheader("ETag")
            observation["etag"] = etag if isinstance(etag, str) and len(etag) <= 256 else None
            raw = response.read(self.http["max_response_bytes"] + 1)
            if len(raw) > self.http["max_response_bytes"]:
                observation["transport_error"] = "RESPONSE_TOO_LARGE"
            elif 300 <= response.status < 400:
                observation["transport_error"] = "REDIRECT_FORBIDDEN"
            elif not observation["content_type"] or not observation["content_type"].startswith("application/json"):
                observation["transport_error"] = "NON_JSON_RESPONSE"
            else:
                parsed = strict_json(raw)
                if type(parsed) not in (dict, list):
                    observation["transport_error"] = "JSON_TOP_LEVEL_INVALID"
                else:
                    from .config_http_contracts import digest
                    observation["response"] = parsed
                    observation["response_body_sha256"] = digest(parsed)
                    if type(parsed) is dict:
                        trace_id = parsed.get("traceId")
                        if isinstance(trace_id, str) and len(trace_id) <= 128:
                            observation["trace_id"] = trace_id
        except TimeoutError:
            observation["transport_error"] = "TIMEOUT"
        except (ConnectionError, OSError, http.client.HTTPException):
            observation["transport_error"] = "CONNECTION_OR_PROTOCOL_ERROR"
        except AdapterRejected:
            raise
        except Exception:
            # Do not copy implementation exception text into evidence or logs.
            observation["transport_error"] = "RESPONSE_PARSE_ERROR"
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            observation["elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000))
            self.observations.append(observation)
        return observation


class ConfigToolHost:
    """The write-only business Tool host. It exposes one fixed POST operation."""

    def __init__(self, contracts: FrozenContracts, api_key: str,
                 observations: list[dict] | None = None):
        _require(isinstance(api_key, str) and _CREDENTIAL.fullmatch(api_key) is not None,
                 "API_KEY_SHAPE")
        self._api_key = api_key
        self._client = _BoundedHttpClient(contracts, observations)
        self.effect = self._client.effect

    def upsert(self, *, kind: str, value: str, expected_version: int | None = None,
               credential_override: str | None = None) -> dict:
        allowed = {
            "unauthorized_write": (self.effect["unauthorized_value"], None),
            "create_v1": (self.effect["initial_value"], None),
            "update_v2": (self.effect["required_value"], self.effect["initial_version"]),
            "stale_update": (self.effect["stale_value"], self.effect["stale_expected_version"]),
        }
        if kind not in allowed or (value, expected_version) != allowed[kind]:
            raise AdapterRejected("UPSERT_INTENT_NOT_ALLOWLISTED")
        if credential_override is not None and kind != "unauthorized_write":
            raise AdapterRejected("CREDENTIAL_OVERRIDE_NOT_ALLOWLISTED")
        body = {name: self.effect[name] for name in ("app", "env", "key")}
        body["value"] = value
        if expected_version is not None:
            body["expectedVersion"] = expected_version
        key = self._api_key if credential_override is None else credential_override
        if not isinstance(key, str) or _CREDENTIAL.fullmatch(key) is None:
            raise AdapterRejected("CREDENTIAL_SHAPE")
        return self._client.request(kind, "POST", "/api/configs", request=body, credential=key)


class ConfigAuthorityReader:
    """Read-only current/history/list adapter; it has no write method or secret."""

    def __init__(self, contracts: FrozenContracts, observations: list[dict] | None = None):
        self._client = _BoundedHttpClient(contracts, observations)
        self.effect = self._client.effect
        app, env, key = (quote(self.effect[name], safe="") for name in ("app", "env", "key"))
        self._current = f"/api/configs/{key}?app={app}&env={env}"
        self._history = f"/api/configs/history?app={app}&env={env}&key={key}&limit=50"
        self._list = f"/api/configs?app={app}&env={env}"

    def get_one(self, *, kind: str) -> dict:
        if kind not in ("initial_current", "after_unauthorized_current", "final_current"):
            raise AdapterRejected("READ_KIND_NOT_ALLOWLISTED")
        return self._client.request(kind, "GET", self._current)

    def get_history(self, *, kind: str) -> dict:
        if kind not in ("initial_history", "after_unauthorized_history", "final_history"):
            raise AdapterRejected("READ_KIND_NOT_ALLOWLISTED")
        return self._client.request(kind, "GET", self._history)

    def list_configs(self) -> dict:
        return self._client.request("final_list", "GET", self._list)
