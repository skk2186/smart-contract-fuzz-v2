#!/usr/bin/env bash
# Deploy + seed the RWA stack on Base Sepolia. Sources .env (secrets stay off the
# command line), verifies the chain and that DEMO_DEPLOYER_PK derives to DEMO_DEPLOYER_ADDR
# before spending gas, then broadcasts the deploy script and (if a Basescan key
# is present) verifies the source.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\033[0;36m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[deploy]\033[0m %s\n' "$*" >&2; }
die() {
	printf '\033[0;31m[deploy] %s\033[0m\n' "$*" >&2
	exit 1
}

# Prefer ./.env, fall back to ../.env (the one-directory-above convention).
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
	log "No .env found. Copy .env.example to .env and populate it. Nothing to do."
	exit 0
fi

: "${DEMO_DEPLOYER_PK:?DEMO_DEPLOYER_PK is required}"
: "${DEMO_DEPLOYER_ADDR:?DEMO_DEPLOYER_ADDR is required}"
: "${DEMO_INVESTOR_A_ADDR:?DEMO_INVESTOR_A_ADDR is required}"
# DEMO_RPC_URL wins when set — sepolia.base.org rate-limits a host that has been
# running the chain suites and then fails as a bare "fetch failed", not a 429.
RPC="${DEMO_RPC_URL:-${RPC_URL:-https://sepolia.base.org}}"

# Verify the RPC really is Base Sepolia (belt-and-braces with the in-script guard).
chain_id="$(cast chain-id --rpc-url "$RPC")"
[ "$chain_id" = "84532" ] || die "RPC chain id is $chain_id, expected 84532 (Base Sepolia)"

# Verify the key derives to the expected address without ever printing the key.
derived="$(cast wallet address --private-key "$DEMO_DEPLOYER_PK")"
[ "${derived,,}" = "${DEMO_DEPLOYER_ADDR,,}" ] || die "DEMO_DEPLOYER_PK derives to $derived, not DEMO_DEPLOYER_ADDR ($DEMO_DEPLOYER_ADDR)"

bal="$(cast balance "$DEMO_DEPLOYER_ADDR" --rpc-url "$RPC" --ether)"
log "Deployer $DEMO_DEPLOYER_ADDR balance: $bal ETH"

verify_args=()
if [ -n "${ETHERSCAN_API_KEY:-}" ]; then
	verify_args=(--verify --etherscan-api-key "$ETHERSCAN_API_KEY" --verifier etherscan)
	log "Basescan verification enabled."
else
	warn "ETHERSCAN_API_KEY unset — deploying without source verification."
fi

log "Broadcasting Deploy.s.sol to Base Sepolia..."
NODE_OPTIONS=--dns-result-order=ipv4first \
	forge script script/Deploy.s.sol:Deploy \
	--rpc-url "$RPC" \
	--broadcast \
	"${verify_args[@]}"

log "Done. Transcribe the printed addresses into deployments/base-sepolia.json + README."
