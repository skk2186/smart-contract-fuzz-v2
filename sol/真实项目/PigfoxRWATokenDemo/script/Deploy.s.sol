// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {IdentityRegistry} from "../src/IdentityRegistry.sol";
import {AssetRegistry} from "../src/AssetRegistry.sol";
import {PriceOracle} from "../src/PriceOracle.sol";
import {RWAToken} from "../src/RWAToken.sol";
import {Redemption} from "../src/Redemption.sol";

/// @notice Deploys the RWA tokenization stack to Base Sepolia and wires it, then
///         seeds the compliant on-chain state the demo page reads: whitelists
///         the deployer and Investor A, registers a batch of backing assets,
///         pushes an oracle price, and mints fractions to Investor A.
/// @dev Reads the deployer key from `DEMO_DEPLOYER_PK` (env, never argv) and
///      Investor A's address from `DEMO_INVESTOR_A_ADDR`. Refuses to run on any chain but
///      Base Sepolia. The Investor-A-signed narrative txs (a successful
///      transfer, the reverting transfer to the un-whitelisted Investor B, and a
///      redemption) are executed afterward by scripts/seed-investor.sh, which
///      holds Investor A's key.
contract Deploy is Script {
    uint256 internal constant BASE_SEPOLIA_CHAIN_ID = 84532;

    /// @notice Tokens minted to Investor A on deploy (10,000 whole tokens).
    uint256 internal constant SEED_MINT = 10_000 ether;
    /// @notice Seed oracle price, in USD cents per token (i.e. $1.05).
    uint256 internal constant SEED_PRICE_CENTS = 105;

    /// @notice The wrong-chain guard.
    error WrongChain(uint256 expected, uint256 actual);

    function run() external {
        if (block.chainid != BASE_SEPOLIA_CHAIN_ID) {
            revert WrongChain(BASE_SEPOLIA_CHAIN_ID, block.chainid);
        }

        // Unified role keys, shared by all three demo repos. See
        // pigfox2-repos/KEYS.md for the addresses and what each role may do.
        uint256 deployerKey = vm.envUint("DEMO_DEPLOYER_PK");
        address deployer = vm.addr(deployerKey);
        address investorA = vm.envAddress("DEMO_INVESTOR_A_ADDR");

        vm.startBroadcast(deployerKey);

        // Deploy.
        IdentityRegistry identity = new IdentityRegistry(deployer);
        AssetRegistry assets = new AssetRegistry(deployer);
        PriceOracle oracle = new PriceOracle(deployer);
        RWAToken token = new RWAToken("Acme Tower Fractions", "ACME", address(identity), deployer);
        Redemption redemption = new Redemption(address(token), address(assets), deployer);

        // Wire the compliance relationships.
        identity.setToken(address(token));
        token.setRedeemer(address(redemption));

        // Whitelist the two KYC-verified parties (deployer + Investor A). Investor
        // B is deliberately left un-whitelisted so the demo's transfer to it reverts.
        identity.registerIdentity(deployer);
        identity.registerIdentity(investorA);

        // Register the backing assets. Enough rows to page the "all assets" table.
        string[12] memory uris = _assetUris();
        for (uint256 i = 0; i < uris.length; i++) {
            assets.registerAsset(keccak256(bytes(uris[i])), uris[i]);
        }

        // Seed the oracle and mint fractions to Investor A.
        oracle.setPrice(SEED_PRICE_CENTS);
        token.mint(investorA, SEED_MINT);

        vm.stopBroadcast();

        console2.log("IdentityRegistry:", address(identity));
        console2.log("AssetRegistry:   ", address(assets));
        console2.log("PriceOracle:     ", address(oracle));
        console2.log("RWAToken:        ", address(token));
        console2.log("Redemption:      ", address(redemption));
        console2.log("Deployer:        ", deployer);
        console2.log("Investor A:      ", investorA);
    }

    /// @dev Realistic metadata URIs for the seeded assets. The document hash of
    ///      each is the keccak of its URI, so the seed is fully deterministic.
    function _assetUris() internal pure returns (string[12] memory uris) {
        uris[0] = "ipfs://bafy-acme-tower-manhattan-office-deed";
        uris[1] = "ipfs://bafy-lakeside-logistics-warehouse-title";
        uris[2] = "ipfs://bafy-solar-farm-nevada-ppa-bundle";
        uris[3] = "ipfs://bafy-vineyard-estate-napa-land-grant";
        uris[4] = "ipfs://bafy-marina-berths-portfolio-lease";
        uris[5] = "ipfs://bafy-datacenter-ashburn-colocation-note";
        uris[6] = "ipfs://bafy-timberland-oregon-parcel-registry";
        uris[7] = "ipfs://bafy-hotel-riverfront-revenue-share";
        uris[8] = "ipfs://bafy-wind-portfolio-texas-turbine-set";
        uris[9] = "ipfs://bafy-student-housing-austin-reit-slice";
        uris[10] = "ipfs://bafy-cold-storage-chicago-facility-lien";
        uris[11] = "ipfs://bafy-fiber-network-metro-ring-easement";
    }
}
