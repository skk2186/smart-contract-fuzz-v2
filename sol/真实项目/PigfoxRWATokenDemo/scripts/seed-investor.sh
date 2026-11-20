#!/usr/bin/env bash
# Investor-A-signed narrative seed, run AFTER scripts/deploy.sh. Reproduces the
# three demo txs the page pins: a compliant transfer, the reverting transfer to
# the un-whitelisted Investor B (the showcase compliance-block), and a
# redemption. Reads addresses from deployments/base-sepolia.json. Read-verifies
# the assumed state before each write (never-assume-verify).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\033[0;36m[seed]\033[0m %s\n' "$*"; }
die() {
	printf '\033[0;31m[seed] %s\033[0m\n' "$*" >&2
	exit 1
}

if [ -f .env ]; then
	set -a
	# shellcheck disable=SC1091
	. ./.env
	set +a
elif [ -f ../.env ]; then
	set -a
	# shellcheck disable=SC1091
	. ../.env
	set +a
else
	die "No .env found."
fi

: "${DEMO_INVESTOR_A_PK:?DEMO_INVESTOR_A_PK required}"
: "${DEMO_INVESTOR_A_ADDR:?DEMO_INVESTOR_A_ADDR required}"
: "${DEMO_INVESTOR_B_ADDR:?DEMO_INVESTOR_B_ADDR required}"
: "${DEMO_DEPLOYER_ADDR:?DEMO_DEPLOYER_ADDR (deployer) required}"
# DEMO_RPC_URL wins when set — see the note in scripts/deploy.sh.
RPC="${DEMO_RPC_URL:-${RPC_URL:-https://sepolia.base.org}}"

D=deployments/base-sepolia.json
TOKEN="$(python3 -c "import json;print(json.load(open('$D'))['contracts']['RWAToken'])")"
REDEEM="$(python3 -c "import json;print(json.load(open('$D'))['contracts']['Redemption'])")"
IDREG="$(python3 -c "import json;print(json.load(open('$D'))['contracts']['IdentityRegistry'])")"
ASSETS="$(python3 -c "import json;print(json.load(open('$D'))['contracts']['AssetRegistry'])")"

ONE_K=1000000000000000000000  # 1,000e18
HALF_K=500000000000000000000  # 500e18
TWO_K=2000000000000000000000  # 2,000e18

export NODE_OPTIONS=--dns-result-order=ipv4first

# --- read-verify ---
[ "$(cast call "$IDREG" 'isVerified(address)(bool)' "$DEMO_INVESTOR_A_ADDR" --rpc-url "$RPC")" = "true" ] ||
	die "Investor A is not verified; deploy/seed did not run."
[ "$(cast call "$IDREG" 'isVerified(address)(bool)' "$DEMO_INVESTOR_B_ADDR" --rpc-url "$RPC")" = "false" ] ||
	die "Investor B is verified — the revert demo would not revert."
[ "$(cast call "$ASSETS" 'isActive(uint256)(bool)' 0 --rpc-url "$RPC")" = "true" ] ||
	die "Asset 0 is not active."

log "Investor A -> deployer, 1,000 ACME (expect success)..."
cast send "$TOKEN" 'transfer(address,uint256)' "$DEMO_DEPLOYER_ADDR" "$ONE_K" \
	--private-key "$DEMO_INVESTOR_A_PK" --rpc-url "$RPC" >/dev/null
log "  done."

log "Investor A -> Investor B, 500 ACME (expect ON-CHAIN REVERT; forced past gas estimation)..."
cast send "$TOKEN" 'transfer(address,uint256)' "$DEMO_INVESTOR_B_ADDR" "$HALF_K" \
	--private-key "$DEMO_INVESTOR_A_PK" --rpc-url "$RPC" --gas-limit 120000 >/dev/null 2>&1 ||
	log "  reverted as intended (recipient not KYC-verified)."

log "Investor A redeems 2,000 ACME against asset 0 (expect success)..."
cast send "$REDEEM" 'requestRedemption(uint256,uint256)' 0 "$TWO_K" \
	--private-key "$DEMO_INVESTOR_A_PK" --rpc-url "$RPC" >/dev/null
log "  done. Narrative seed complete."
