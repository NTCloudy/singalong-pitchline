"""Local preview server. Development only; not part of the site.

Serves the project folder on 127.0.0.1 so the page has an http origin (YouTube's
player and the microphone both need one; opening the file directly does not work).

Usage: python3 -m tools.serve [port]     then open http://127.0.0.1:8770/docs/
"""
import functools
import http.server
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    httpd = http.server.ThreadingHTTPServer((HOST, port), functools.partial(Handler, directory=str(ROOT)))
    print(f"http://{HOST}:{httpd.server_address[1]}/docs/  (Ctrl-C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
