# Deploying to AWS

The shape of it:

```
Browser ──HTTPS──> CloudFront ──┬── default (*)  ──> S3 bucket (React build, private, OAC)
                                └── /api/*       ──> EC2 :8000 (Python API) ──> MongoDB Atlas
```

**One distribution, two origins.** That is the decision everything else follows
from. The frontend calls `/api` as a relative path (`frontend/src/lib/api.js`),
so routing `/api/*` through the same CloudFront domain means the browser sees a
single origin: no CORS on the hot path, no second certificate, and **no frontend
code changes at all**.

It also sidesteps a problem that has no cheap answer. CloudFront is HTTPS and a
bare EC2 instance is HTTP, and browsers block an HTTPS page from calling an HTTP
API. Putting a real certificate on the backend would need a domain you own,
because ACM will not issue one for `*.amazonaws.com`. CloudFront talks HTTPS to
the browser and plain HTTP back to the instance, so the problem does not arise.

> This file is a runbook, not a presentation artifact - it is long because it is
> followed step by step rather than read. See AGENTS.md on document length.

Pick one region and use it for everything below. `eu-west-1` in the examples;
substitute yours. The one exception is ACM, which must be `us-east-1` for
CloudFront - only relevant if you add a custom domain.

---

## Step 0 - Before the console

Generate a **production** signing key. Do not reuse the one in your `.env`; that
one is personal to your machine and is in your shell history.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Have ready: your Atlas `MONGODB_URI`, and your `BANK_ADMIN_CODE`.

**If your GitHub repo is private**, `bootstrap.sh` cannot clone it. Either make
it public, or create a fine-grained PAT with read-only Contents access and clone
via `https://<token>@github.com/...`. A PAT in shell history on a shared box is
worth avoiding - public is simpler for a training project.

---

## Step 1 - Parameter Store

**Systems Manager -> Parameter Store -> Create parameter**, five times. Tier
Standard throughout.

| Name | Type | Value |
| --- | --- | --- |
| `/simplebank/MONGODB_URI` | SecureString | your Atlas connection string |
| `/simplebank/MONGODB_DB` | String | `simple_bank` |
| `/simplebank/BANK_SECRET` | SecureString | the key from Step 0 |
| `/simplebank/BANK_ADMIN_CODE` | SecureString | your team code |
| `/simplebank/BANK_CORS_ORIGIN` | String | `*` for now - Step 8 replaces it |

The `/simplebank/` prefix is not decoration: `bootstrap.sh` fetches the whole
path with one `get-parameters-by-path` and strips the prefix to make environment
variable names, and the IAM policy below scopes to exactly that prefix.

---

## Step 2 - The instance role

**IAM -> Roles -> Create role**, trusted entity *AWS service*, use case *EC2*.

Attach the AWS managed policy **`AmazonSSMManagedInstanceCore`**. This is what
lets you connect with Session Manager - a browser shell, no SSH key to lose and
no port 22 open to the internet.

Then **Add permissions -> Create inline policy -> JSON**, replacing `REGION` and
`ACCOUNT_ID`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
      "Resource": "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/simplebank/*"
    },
    {
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "*",
      "Condition": { "StringEquals": { "kms:ViaService": "ssm.REGION.amazonaws.com" } }
    }
  ]
}
```

The `kms:Decrypt` half is the one people miss. `AmazonSSMReadOnlyAccess` alone
returns the SecureStrings still encrypted, and the failure reads as a connection
string that looks like line noise.

Name it `SimpleBankInstanceRole`.

---

## Step 3 - EC2

**EC2 -> Launch instance.**

- **AMI** Amazon Linux 2023
- **Type** `t3.micro`
- **Key pair** *Proceed without a key pair* - Session Manager replaces it
- **Network** default VPC, a public subnet, **auto-assign public IP: Enable**
- **Security group** create `simplebank-api-sg`, one inbound rule:
  Custom TCP, port **8000**, source **My IP**. Step 8 tightens this.
- **Advanced details -> IAM instance profile** `SimpleBankInstanceRole`

Launch. Then **Elastic IPs -> Allocate**, and **Associate** it with the instance.

The Elastic IP is not optional here. It pins both the public IP (which Atlas
allowlists) and the public DNS name (which CloudFront uses as its origin).
Without it, stopping and starting the instance silently breaks both.

---

## Step 4 - Let Atlas accept the instance

Atlas -> **Network Access -> Add IP Address** -> the Elastic IP, `/32`.

Skipping this produces a server that starts, connects to nothing, and reports
`could not reach the cluster`.

---

## Step 5 - Build the runtime

**EC2 -> select instance -> Connect -> Session Manager -> Connect.**

```bash
sudo dnf install -y git
sudo REGION=eu-west-1 \
     REPO=https://github.com/D4DavidG/SimpleBankApplicationG2.git \
     bash -c 'git clone --depth 1 "$REPO" /tmp/bs && bash /tmp/bs/deploy/bootstrap.sh'
```

`bootstrap.sh` installs python3.11 (AL2023 ships 3.9; the codebase uses
`str | None` annotations, which are evaluated at import time and need 3.10+),
creates a venv, writes `/etc/simplebank/bank.env` from Parameter Store, installs
the systemd unit and starts it. It is idempotent - re-run it to redeploy after a
push.

It ends with a health check. If that fails: `journalctl -u bank-api -n 50`.

Confirm the runtime is genuinely sound before going further:

```bash
cd /opt/simplebank && sudo -u bankapi .venv/bin/python -m unittest -q
curl -s http://127.0.0.1:8000/api/health
```

Then from **your own machine**, proving the security group and Elastic IP work:

```powershell
curl http://<ELASTIC-IP>:8000/api/health
```

---

## Step 6 - S3 and the frontend build

**S3 -> Create bucket.** Name it something unique (`simplebank-site-david`).
Leave **Block all public access ON** - CloudFront reaches it through Origin
Access Control, so the bucket never needs to be public. Everything else default.

Build and upload:

```powershell
cd frontend
npm ci
npm run build
```

Upload the **contents** of `frontend/dist/` - `index.html` and the `assets/`
folder - to the bucket root. Not the `dist` folder itself; `index.html` must sit
at the top of the bucket.

`deploy/publish-frontend.ps1` does this plus cache headers and invalidation,
once you have CLI credentials and the distribution id.

---

## Step 7 - CloudFront

**CloudFront -> Create distribution.**

**Origin 1 - the site**

- Origin domain: your S3 bucket, picked from the list - *not* the website
  endpoint
- Origin access: **Origin access control settings** -> Create new OAC -> accept
- CloudFront then shows a bucket policy to copy. **Do it** - *Copy policy*, then
  S3 -> bucket -> Permissions -> Bucket policy -> paste. Until you do, every
  request is 403.

**Default cache behaviour**

- Viewer protocol policy: **Redirect HTTP to HTTPS**
- Allowed methods: GET, HEAD
- Cache policy: **CachingOptimized**

**Settings**

- Default root object: **`index.html`**
- **Do not set custom error responses.** Every SPA tutorial tells you to map 403
  and 404 to `/index.html` with a 200. It applies to the whole distribution,
  including `/api/*` - and this API returns 404 for "that account is not yours"
  and 403 for NotAuthorized. Both would arrive as 200 with a page of HTML,
  `lib/api.js` would try to `JSON.parse` the app shell, and every permission
  check in the product would appear to pass. Step 7b handles SPA routing without
  it.

Create it, then add the second origin.

**Origin 2 - the API.** *Origins -> Create origin*

- Origin domain: the instance's **public IPv4 DNS**
  (`ec2-1-2-3-4.eu-west-1.compute.amazonaws.com`)
- Protocol: **HTTP only**
- **HTTP port: 8000**

**Behaviour for the API.** *Behaviors -> Create behavior*

- Path pattern: **`/api/*`**
- Origin: origin 2
- Viewer protocol policy: Redirect HTTP to HTTPS
- Allowed methods: **GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE**
- **Cache policy: `CachingDisabled`**
- **Origin request policy: `AllViewerExceptHostHeader`**

Those last two are the ones that break things silently. `CachingOptimized`
strips the `Authorization` header and caches responses, so every authenticated
call 401s and one user's balance can be served to the next. Without the origin
request policy the token never reaches the instance at all.

Check `/api/*` sits **above** `Default (*)` in the behaviours list. It will.

**Step 7b - SPA routing.** *CloudFront -> Functions -> Create function*, name
`spa-router`, runtime cloudfront-js-2.0. Paste `deploy/spa-router.js`.
**Publish** it, then *Associate* -> your distribution -> the **Default (\*)**
behaviour -> **Viewer request**.

Associating it with `Default (*)` and not `/api/*` is the whole point.

Wait for the distribution to finish deploying (~5 minutes), then note the domain
name: `https://d1234abcd.cloudfront.net`.

---

## Step 8 - Lock the backend down, and set CORS

Right now port 8000 is open to your IP, and CloudFront cannot reach it from
anywhere else. Fix both ends.

**EC2 -> Security Groups -> `simplebank-api-sg` -> Edit inbound rules.** Delete
the *My IP* rule. Add: Custom TCP, port 8000, Source **Custom** -> type
`cloudfront` -> pick **`com.amazonaws.global.cloudfront.origin-facing`**.

The instance now answers CloudFront and nothing else. Direct `http://<ip>:8000`
stops working - that is the intended result, and it is what makes the deployment
HTTPS-only in practice.

**Then set the CORS origin.** Parameter Store -> `/simplebank/BANK_CORS_ORIGIN`
-> your `https://d1234abcd.cloudfront.net`, no trailing slash. On the instance:

```bash
sudo bash /opt/simplebank/deploy/bootstrap.sh
sudo systemctl restart bank-api
sudo journalctl -u bank-api -n 30 | grep CORS
```

Worth being straight about what this does. Because the browser calls the API on
the same origin it loaded the page from, it never sends an `Origin` header on
the hot path - so CORS is not what makes the app work. What it does is stop a
page on any *other* site from calling your API through CloudFront with a stolen
token. It is defence in depth, not plumbing, and `server.py` prints the active
setting at boot so it can be shown to be on.

---

## Step 9 - End-to-end verification

Against `https://d1234abcd.cloudfront.net`:

| Check | How | Proves |
| --- | --- | --- |
| API reachable | `curl https://.../api/health` | origin 2, port 8000, security group |
| App loads | open the root | S3 origin, OAC, bucket policy |
| **Deep link** | open `/accounts` **directly**, then hard-refresh | `spa-router` - the fix most likely to be missed |
| **Auth survives** | log in as `aaron.forrester@example.com` / `BankDemo123!` | `AllViewerExceptHostHeader` forwards `Authorization` |
| **Not cached** | check a balance, deposit, check it again | `CachingDisabled` on `/api/*` |
| Ownership still 404s | as a customer, `GET /api/accounts/1` for an account you do not own | custom error responses are genuinely absent |
| Ledger intact | log in as admin -> `GET /api/admin/reconciliation` | `balanced: true` after a network round trip |
| Survives reboot | reboot the instance from the console, wait, re-check health | the systemd unit is enabled |

The deep-link and ownership rows are the two a casual click-through misses, and
both are load-bearing for this product.

---

## Redeploying

**Backend:** `sudo bash /opt/simplebank/deploy/bootstrap.sh` - pulls, reinstalls,
restarts.

**Frontend:** `./deploy/publish-frontend.ps1 -Bucket <name> -DistributionId <id>`,
or rebuild and re-upload by hand. Either way **invalidate `/index.html`**, or
CloudFront keeps serving the previous build for up to 24 hours.

---

## Known limitations

- **`http.server` is not a production server**, and `bank/api.py` says so in its
  own docstring. It is one process with a thread per request. Fine for a graded
  demo behind CloudFront; a real deployment puts gunicorn or an ASGI server
  here, which is a rewrite of `serve()` and nothing else.
- **One instance, no autoscaling.** A reboot is ~60 seconds of downtime.
- **No custom domain.** Add ACM in `us-east-1`, Route 53, and an alternate
  domain name on the distribution. Nothing above changes.
- **DocumentDB was not used.** The phase allows "Amazon DocumentDB / Managed
  MongoDB cluster" and Atlas is the latter. DocumentDB would need TLS with the
  RDS CA bundle, `retryWrites=false`, a VPC route, and a replacement for the
  `partialFilterExpression` index in `bank/mongo_store.py` that guarantees
  `clientTxnId` idempotency - it does not support partial indexes.
