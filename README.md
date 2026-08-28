# task-mcp-server

Small MCP server that sits in front of a task-tracking REST API I have running elsewhere (`task-service`) and exposes it as tools — `get_all_tasks`, `claim_task`, `complete_task`, `approve_task`, that kind of thing. I use it with Claude Code so I can claim/finish/review tasks from chat instead of curling the API or clicking through a UI.

Built mostly to actually understand how MCP auth is supposed to work, not just to have a working integration. So instead of a static token in an env var, it's proper OAuth 2.1 through Cognito — every call is tied to whoever logged in, not to "the bot."

## How it's wired

```
Claude Code (MCP client)
  -> API Gateway
    -> Lambda (Mangum adapter -> FastMCP)
      -> task-service
```

Lambda + API Gateway via SAM. Mangum's job is just turning API Gateway's event format into something FastMCP's ASGI app understands, nothing fancier than that. Locally I run the same `mcp.http_app()` object through uvicorn directly — same code, Mangum swapped out.

Auth-wise: first request with no token gets a 401 pointing at `/.well-known/oauth-protected-resource`, the client reads that to find out Cognito is the issuer, does the browser OAuth dance, comes back with a JWT, and from then on every tool call carries that token straight through to `task-service`.

## The auth part (and where I cut corners)

`RemoteAuthProvider` from FastMCP does most of the heavy lifting here — it's the thing that serves the protected-resource metadata and checks incoming JWTs against Cognito's JWKS. I didn't write an OAuth server, Cognito issues tokens and I just verify them.

Thing that actually tripped me up: I assumed Cognito access tokens would have an `aud` claim like a normal OIDC token, so I could just tell the verifier "only accept tokens for this audience" and be done with it. They don't — only `client_id`. So there's a manual `token.client_id == settings.cognito_app_client_id` check in `_auth_headers()` before I forward anything. Found that out by staring at a decoded JWT for way too long wondering why the audience field was empty.

Corner I knowingly cut: there's one Cognito app client and everyone who authenticates through it gets treated the same way, resource-wise. No token exchange, no separate audiences per resource server. Fine when you've got one MCP server behind one user pool. If I ever bolt a second resource server onto the same pool I'd have to actually deal with that — right now I'm not pretending I did.

## Running it locally

```bash
cp .env.example .env   # fill in your Cognito pool/client + task-service url
uv sync
uv run mcp_server.py
```

Runs on `127.0.0.1:8000`. `.env` only gets read locally (`config.py`, via pydantic-settings) — the deployed Lambda gets the same variable names from CloudFormation instead, so there's no file to accidentally mix up between the two.

## Deploying

```bash
sam build
sam deploy
```

`samconfig.toml` isn't in the repo (real Cognito IDs live there, see `samconfig.toml.example` for the shape) — copy it and fill in your own.

One annoying thing about the first deploy: `MCP_RESOURCE_SERVER_URL` needs to be the API Gateway URL the stack will actually be reachable at, but you can't pull that in with `!Sub` from inside the function's own environment variables — CloudFormation doesn't like a resource referencing something being created in the same stack as itself, circular dependency. Works fine in `Outputs`, just not there. So it's deploy once, grab the URL from the stack output, stick it in `samconfig.toml`, deploy again. Only bites once per environment at least.

## Connecting from Claude Code

```json
{
  "mcpServers": {
    "task-work-service": {
      "type": "http",
      "url": "https://<your-api-id>.execute-api.<region>.amazonaws.com/mcp",
      "oauth": {
        "clientId": "<your-cognito-app-client-id>",
        "callbackPort": 7777
      }
    }
  }
}
```

`callbackPort` has to match a redirect URI you've actually added to the Cognito app client (`http://localhost:<port>/callback`) — Cognito checks that exactly, no fuzzy matching. Then `/mcp` in Claude Code, authenticate, it opens the Cognito login page in your browser.

## Stack

Python 3.12, FastMCP, Mangum, AWS SAM (Lambda + HttpApi), Cognito, httpx, pydantic-settings, `uv` for deps.
