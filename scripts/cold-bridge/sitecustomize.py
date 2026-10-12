"""Worker-only SDK transport shim. Real credentials never enter this process."""

import json
import os
import time
import uuid
from pathlib import Path

if os.environ.get("COLD_BRIDGE_DIR"):
    import httpx
    from jev_context import provider

    class FileTransport(httpx.BaseTransport):
        def handle_request(self, request):
            if request.method != "POST" or request.url != "https://api.typesafe.ai/v1/systemone":
                raise httpx.TransportError("cold_bridge_endpoint_not_allowed")
            root = Path(os.environ["COLD_BRIDGE_DIR"])
            identifier = uuid.uuid4().hex
            packet = {"id": identifier, "body": json.loads(request.content)}
            temporary = root / "requests" / (identifier + ".pending")
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(packet, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.rename(root / "requests" / (identifier + ".json"))
            response = root / "responses" / (identifier + ".json")
            deadline = time.monotonic() + float(os.environ.get("COLD_BRIDGE_TIMEOUT", "100"))
            while time.monotonic() < deadline:
                if response.is_file():
                    result = json.loads(response.read_text())
                    return httpx.Response(
                        result["status"],
                        json=result["body"],
                        headers=result.get("headers", {}),
                        request=request,
                    )
                time.sleep(0.02)
            raise httpx.TransportError("cold_bridge_response_unknown")

    original = provider.Client.__init__

    def init(self, **kwargs):
        kwargs["api_key"] = "cold-bridge-placeholder"
        kwargs["transport"] = FileTransport()
        original(self, **kwargs)

    provider.Client.__init__ = init
