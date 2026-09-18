# Deploying

The React build is static files on S3; the API is one Lambda function. CloudFront
serves both, so the browser sees one origin and there is no CORS to configure.

## Backend

```bash
python tools/build_lambda.py        # writes dist/lambda.zip
```

Python 3.12 function, handler `lambda_handler.lambda_handler`, timeout 30s, with
an API Gateway HTTP API or a Function URL in front.

Three environment variables, all required. The function returns a 503 naming any
that are missing.

| Variable | Why it is not optional |
| --- | --- |
| `BANK_SECRET` | Each container otherwise invents its own signing key, so a token from one is rejected by the next: you log in, and the next request 401s. |
| `MONGODB_URI` | The in-memory store dies with the container, and two containers hold two different banks. |
| `MONGODB_DB` | Your own database, never the shared `simple_bank`. |

`BANK_ADMIN_CODE` is optional; unset shuts admin registration.

Add `0.0.0.0/0` to the Atlas access list. Lambda's egress IP is not stable, and
Atlas drops unknown IPs rather than refusing them, so the symptom is a thirty
second timeout.

**Do not strip the `/api` prefix at the gateway** — every route pattern begins
with it. Check with `curl https://<api>/api/health`, the one route needing no
token.

## Frontend

```bash
cd frontend && npm run build
aws s3 sync dist/ s3://<bucket>/ --delete \
  --exclude index.html --cache-control "public,max-age=31536000,immutable"
aws s3 cp dist/index.html s3://<bucket>/index.html --cache-control "no-cache"
```

Asset names are content-hashed and cache forever. `index.html` must not, or
visitors keep loading the previous build's hashes.

## CloudFront

Three settings, each fixing a failure that looks like something else:

1. **Default root object** `index.html`. Without it `/` asks S3 for the empty key
   and gets `AccessDenied`, because the policy grants `GetObject`, not
   `ListBucket`.
2. **Custom error responses** 403 and 404 → `/index.html`, status 200. The app
   uses `BrowserRouter`, so `/transfer` is not a key in the bucket.
3. **A `/api/*` behaviour** above the default, pointing at the gateway: all
   methods allowed (the default permits only GET and HEAD, so login fails),
   caching disabled, and an origin request policy forwarding `Authorization`
   (stripped, every authenticated call 401s).

Keep the bucket private behind origin access control, and invalidate `/*` after
any change — CloudFront caches the error too.

Without the `/api/*` behaviour, calls fall through to S3, which answers XML, and
the frontend reports `the server did not answer with JSON`. That error means the
request never reached Lambda.
