"""Serve a deliberately limited, synthetic provider fixture without upstream I/O."""

import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/providers/the_odds_api/odds-success.json"
ODDS_PATH = "/v4/sports/soccer_epl/odds"


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


def resolve_response(target: str, scenario: str, success: bytes) -> Response:
    request = urlsplit(target)
    if request.path == "/health":
        return Response(200, b'{"status":"ok","mode":"synthetic"}\n')
    if request.path != ODDS_PATH:
        return Response(404, b'{"error":"unknown mock route"}\n')
    supported = {"regions": "us", "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso"}
    for key, values in parse_qs(request.query, keep_blank_values=True).items():
        if key != "apiKey" and (key not in supported or values != [supported[key]]):
            return Response(400, b'{"error":"unsupported mock query"}\n')
    responses = {
        "success": Response(200, success),
        "empty": Response(200, b"[]\n"),
        "rate-limit": Response(429, b'{"error":"synthetic rate limit"}\n', (("Retry-After", "1"),)),
        "server-error": Response(503, b'{"error":"synthetic upstream failure"}\n'),
        "malformed": Response(200, b'{"deliberately_invalid_json":'),
    }
    return responses.get(scenario, Response(400, b'{"error":"unknown mock scenario"}\n'))


def handler_for(success: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            response = resolve_response(
                self.path, self.headers.get("X-Mock-Scenario", "success"), success
            )
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("X-Mock-Origin", "synthetic")
            self.send_header("Cache-Control", "no-store")
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            # Do not log request query strings, which may contain test credentials.
            pass

    return Handler


def main() -> None:
    host = os.environ.get("MOCK_PROVIDER_HOST", "127.0.0.1")
    port = int(os.environ.get("MOCK_PROVIDER_PORT", "9080"))
    with ThreadingHTTPServer((host, port), handler_for(FIXTURE.read_bytes())) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
