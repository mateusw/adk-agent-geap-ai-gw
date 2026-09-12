# ADK agent + Agent Gateway + Agent Retrieval

A small, self-contained ADK agent that shows how **Agent Gateway** governs an
agent's traffic, and what that means for how you build tools.

It is one `LlmAgent` over a synthetic product catalog held in **Agent
Retrieval** (Vector Search 2.0). The agent carries three tools that return the
**same data from the same host**, differing only in transport. Ask the same
question three ways, then read the gateway logs and compare.

## The finding

With the gateway in dry-run everything works. Switch enforcement on and it does
not:

| Tool | Transport | Dry-run | Enforcing |
|---|---|---|---|
| `search_data_objects` | MCP over HTTPS | works | **works** |
| `search_catalog_rest` | plain HTTPS / REST | works | **works** |
| `search_catalog_sdk` | gRPC (client library) | works | **403 denied** |

**Under an enforcing gateway an agent's tools must speak HTTP/JSON, not gRPC.**
Both are TLS on 443 — the difference is framing, not encryption. Most Google
client libraries default to gRPC, so a tool inherits it without anyone choosing
it, then breaks the day governance is turned on rather than the day it was
written. Those same APIs almost always expose a REST form of the method, which
is usually the smallest fix.

Choose MCP when you also want per-tool policy: the gateway parses MCP and logs
the method and tool name, so egress rules can say *which tool* rather than
*which host*.

## Layout

```
common/          config and the three tools: MCP, REST, client library (gRPC)
catalog_agent/   the agent
data/            synthetic catalog and its idempotent loader
deploy/          gateway pair, registry entries and IAM, deploy, teardown
scripts/         query the deployed agent, read back the gateway logs
```

## Prerequisites

- A Google Cloud project with Agent Gateway and Agent Retrieval enabled. Both
  are **Preview**, under the Pre-GA Offerings Terms.
- APIs: `aiplatform`, `vectorsearch`, `networkservices`, `networksecurity`,
  `agentregistry`, `iap`, `modelarmor`, `logging`.
- A Cloud Storage bucket for staging.
- Python 3.12 and `gcloud`.

## Quickstart

```bash
cp .env.example .env      # set GOOGLE_CLOUD_PROJECT and STAGING_BUCKET
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python data/vectorsearch_setup.py
```

Embeddings are generated server-side and asynchronously; allow a minute before
the first search returns results.

**1. Run locally.** Local runs bypass Agent Gateway — only Agent Runtime and
Gemini Enterprise are routed through it — so anything that breaks after this
step is a gateway problem, not an agent one:

```bash
.venv/bin/python run_agent.py --all "a rug I can hose down on a patio"
```

`--all` asks the same question over MCP, REST, then gRPC. Same collection, so
the three replies should match.

**2. Deploy behind the gateways.**

```bash
./deploy/gateways.sh                        # egress + ingress pair, dry-run
./deploy/register.sh                        # register egress destinations
.venv/bin/python deploy/deployer.py         # deploy, bound to both gateways
./deploy/register.sh --grant <ENGINE_ID>    # grant roles/iap.egressor
```

Confirm the binding took — `null` means it silently did not:

```bash
. ./.env                                       # GOOGLE_CLOUD_PROJECT
REGION="${AGENT_ENGINE_LOCATION:-us-central1}"
ENGINE_ID=...                                  # printed by deployer.py

curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://$REGION-aiplatform.googleapis.com/v1/projects/$GOOGLE_CLOUD_PROJECT/locations/$REGION/reasoningEngines/$ENGINE_ID" \
  | jq '.spec.deploymentSpec.agentGatewayConfig'
```

**3. Observe.**

```bash
.venv/bin/python scripts/query_deployed.py --all "a rug for a patio"
.venv/bin/python scripts/gateway_logs.py --mcp-only
```

```
ALLOWED  vectorsearch.googleapis.com   MCP tools/call search_data_objects
ALLOWED  vectorsearch.googleapis.com   MCP tools/list
ALLOWED  vectorsearch.googleapis.com   MCP initialize
```

MCP is attributed down to the tool name. Drop `--mcp-only` and the REST and
gRPC calls show a hostname and nothing more.

Gateway logs take up to ~90 seconds to land, and `tools/call` is usually the
last line to arrive. An empty or partial result right after a query means the
logs have not caught up, not that the call was missed. Re-run with
`--minutes 10`.

**4. Enforce.** `./deploy/gateways.sh --enforce` drops dry-run and sets
`failOpen: false`. Re-run step 3: MCP and REST still answer, gRPC comes back
403 — the table at the top of this file.

**5. Tear down.** `./deploy/teardown.sh` removes the deployed agent, both
gateways with their authorization extensions and policies, the registry
entries, and the collection. It only touches names from `.env`, so a
pre-existing gateway is left alone.

## Gotchas

- **Egress is default-deny on two independent axes.** The destination must be
  registered in Agent Registry, *and* the agent identity needs
  `roles/iap.egressor` on it. Under enforcement, missing either fails every
  invocation — including the platform's own Sessions API calls. Both gateways
  here ship in dry-run for that reason.
- **`identity_type=AGENT_IDENTITY` must be set at creation, and grants no data
  access.** The agent runs as its own principal, not the default service
  account, so it also needs the API roles it uses (`roles/vectorsearch.viewer`,
  `roles/mcp.toolUser`). Reachability and authorization are separate gates.
- **Use `iapPolicyVersion: V1`** unless you have completed Unified Access
  Policy setup. On V2, every egress was denied despite correct `iap.egressor`
  bindings.
- **Packaging.** `extra_packages` paths are relative to the working directory;
  `requirements` is a list of specifiers, not a file path; deploy an
  `AdkApp(app=...)`, not a bare ADK `App`.

## Status

Egress is demonstrated in both dry-run and enforcing modes. **Ingress is
configured but unverified**: the `CLIENT_TO_AGENT` gateway exists, the binding
is present on the reasoning engine, and the agent is registered by its mTLS
URL, yet repeated `streamQuery` calls produced no ingress log entries. Treat
that half as unproven.

Observed on one project, in Preview, where behaviour can change under you.
Re-check before you rely on it.

---

Demonstration code. Not an official Google product, and not intended for
production use. All catalog data is synthetic.
