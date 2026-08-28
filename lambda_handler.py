from mangum import Mangum

from mcp_server import mcp

asgi_app = mcp.http_app(stateless_http=True)
handler = Mangum(asgi_app)
