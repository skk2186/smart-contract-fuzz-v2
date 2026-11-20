// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {IdentityRegistry} from "../src/IdentityRegistry.sol";
import {AssetRegistry} from "../src/AssetRegistry.sol";
import {PriceOracle} from "../src/PriceOracle.sol";
import {RWAToken} from "../src/RWAToken.sol";
import {Redemption} from "../src/Redemption.sol";

/// @dev Shared fixture: deploys the whole RWA system as `owner` (the deployer),
///      wires the registry/token/redemption relationships, and exposes helpers.
///      Deployment happens under `vm.startPrank(owner)` so `owner` is the
///      Roles owner + first agent of every contract, matching production wiring.
abstract contract BaseTest is Test {
    IdentityRegistry internal identity;
    AssetRegistry internal assets;
    PriceOracle internal oracle;
    RWAToken internal token;
    Redemption internal redemption;

    address internal owner = makeAddr("owner");
    address internal alice = makeAddr("alice"); // KYC-verified investor A
    address internal bob = makeAddr("bob"); // KYC-verified investor B
    address internal carol = makeAddr("carol"); // NOT verified
    address internal stranger = makeAddr("stranger"); // neither owner nor agent

    string internal constant TOKEN_NAME = "Acme Tower Fractions";
    string internal constant TOKEN_SYMBOL = "ACME";
    bytes32 internal constant DOC_HASH = keccak256("acme-tower-deed-v1");
    string internal constant DOC_URI = "ipfs://Qm-acme-tower-deed";

    function setUp() public virtual {
        vm.startPrank(owner);
        identity = new IdentityRegistry(owner);
        assets = new AssetRegistry(owner);
        oracle = new PriceOracle(owner);
        token = new RWAToken(TOKEN_NAME, TOKEN_SYMBOL, address(identity), owner);
        redemption = new Redemption(address(token), address(assets), owner);

        identity.setToken(address(token));
        token.setRedeemer(address(redemption));

        identity.registerIdentity(alice);
        identity.registerIdentity(bob);
        vm.stopPrank();
    }

    /// @dev Mint `amount` to a verified `to` as the owner/agent.
    function _mint(address to, uint256 amount) internal {
        vm.prank(owner);
        token.mint(to, amount);
    }

    /// @dev Register an active asset as the owner/agent, returning its id.
    function _registerAsset() internal returns (uint256 id) {
        vm.prank(owner);
        id = assets.registerAsset(DOC_HASH, DOC_URI);
    }
}
