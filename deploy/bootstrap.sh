#!/bin/bash
# Build the backend runtime on a fresh Amazon Linux 2023 instance, then start it.
#
# Run as root. Safe to re-run: every step is idempotent, so this doubles as the
# redeploy script after a `git pull`.
#
#   sudo REGION=eu-west-1 REPO=https://github.com/you/SimpleBankApplicationG2 bash bootstrap.sh
#
# It reads configuration from SSM Parameter Store under /simplebank/ and writes
# it to /etc/simplebank/bank.env, which the systemd unit loads. Nothing secret is
# ever written into the repo checkout.
set -euo pipefail

REGION="${REGION:-$(curl -fsS -m 2 -H "X-aws-ec2-metadata-token: $(
  curl -fsS -m 2 -X PUT http://169.254.169.254/latest/api/token \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
  http://169.254.169.254/latest/meta-data/placement/region)}"
REPO="${REPO:?set REPO to the git clone URL}"
APP_DIR=/opt/simplebank
SSM_PREFIX="${SSM_PREFIX:-/simplebank}"

echo "==> region $REGION, prefix $SSM_PREFIX"

# --- 1. runtime ----------------------------------------------------------
# python3.11, not the system python3: AL2023 ships 3.9, and the codebase uses
# `str | None` annotations, which are evaluated at import time and need 3.10+.
dnf install -y python3.11 python3.11-pip git >/dev/null

id -u bankapi &>/dev/null || useradd --system --home-dir "$APP_DIR" --shell /sbin/nologin bankapi

# --- 2. code -------------------------------------------------------------
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO" "$APP_DIR"
fi

# --- 3. dependencies -----------------------------------------------------
# A venv rather than --user or system pip: it keeps pymongo off the system
# python, so a dnf update cannot change the version the app runs against.
[[ -d "$APP_DIR/.venv" ]] || python3.11 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# --- 4. configuration from Parameter Store -------------------------------
# Fetched at boot rather than baked into the image, so rotating a secret is an
# SSM edit plus a restart, not a rebuild. The instance role grants the read.
install -d -m 0750 -o root -g bankapi /etc/simplebank
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT

aws ssm get-parameters-by-path \
  --path "$SSM_PREFIX" --recursive --with-decryption \
  --region "$REGION" \
  --query 'Parameters[].[Name,Value]' --output text \
| while IFS=$'\t' read -r name value; do
    # /simplebank/MONGODB_URI -> MONGODB_URI. Quoted because systemd splits an
    # unquoted value on whitespace, and a connection string may carry some.
    printf '%s="%s"\n' "${name##*/}" "$value"
  done > "$TMP_ENV"

# Fail loudly rather than starting a server that silently runs in memory with a
# throwaway signing key - both of which look fine until the demo.
for required in MONGODB_URI MONGODB_DB BANK_SECRET; do
  grep -q "^${required}=" "$TMP_ENV" || {
    echo "!! $SSM_PREFIX/$required is missing from Parameter Store" >&2
    exit 1
  }
done

install -m 0640 -o root -g bankapi "$TMP_ENV" /etc/simplebank/bank.env
echo "==> wrote /etc/simplebank/bank.env ($(wc -l < /etc/simplebank/bank.env) settings)"

# --- 5. service ----------------------------------------------------------
chown -R bankapi:bankapi "$APP_DIR"
install -m 0644 "$APP_DIR/deploy/bank-api.service" /etc/systemd/system/bank-api.service
systemctl daemon-reload
systemctl enable --now bank-api
sleep 3
systemctl --no-pager --lines=20 status bank-api || true

echo
echo "==> health check"
curl -fsS http://127.0.0.1:8000/api/health && echo || {
  echo "!! health check failed. Logs: journalctl -u bank-api -n 50" >&2
  exit 1
}
