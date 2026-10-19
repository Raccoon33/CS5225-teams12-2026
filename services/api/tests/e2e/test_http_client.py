"""The deployed-test client must never forward bearer tokens through redirects."""

from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from .conftest import HttpApi


@contextmanager
def serving(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(
            target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
        )
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_cross_origin_redirect_never_receives_credentials(
    status: int, method: str
) -> None:
    received: list[str | None] = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        do_POST = do_GET

        def log_message(self, format: str, *args: object) -> None:
            pass

    with serving(Target) as destination:

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(status)
                self.send_header("Location", destination + "/captured")
                self.end_headers()
                # Redirects can return HTML; the client should retain the status.
                self.wfile.write(b"<p>Redirect</p>")

            do_POST = do_GET

            def log_message(self, format: str, *args: object) -> None:
                pass

        with serving(Redirect) as source:
            reply = HttpApi(source).call(
                method,
                "/groups/example",
                {"name": "Example"} if method == "POST" else None,
                "synthetic-member-token",
            )

    assert received == []
    assert reply.status == status
