// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../HokusaiParams.sol";
import "../HokusaiToken.sol";
import "../interfaces/IHokusaiParams.sol";

contract EchidnaTokenUnauthorizedCaller {
    function tryMintInvestor(HokusaiToken token, address to, uint256 amount) external returns (bool) {
        try token.mintInvestor(to, amount) {
            return true;
        } catch {
            return false;
        }
    }
}

contract EchidnaHokusaiToken {
    uint256 private constant SUPPLIER_ALLOCATION = 1_000 ether;
    uint256 private constant INVESTOR_ALLOCATION = 9_000 ether;
    uint256 private constant MAX_FUZZ_MINT = 250 ether;
    address private constant USER_A = address(0x1001);
    address private constant USER_B = address(0x1002);
    address private constant VESTING_VAULT = address(0x1003);

    HokusaiParams public params;
    HokusaiToken public token;
    EchidnaTokenUnauthorizedCaller private unauthorizedCaller;

    uint256 private expectedSupply;
    bool private supplierDistributedSeen;
    bool private unauthorizedMintSucceeded;

    constructor() {
        IHokusaiParams.VestingConfig memory vestingConfig = IHokusaiParams.VestingConfig({
            enabled: false,
            immediateUnlockBps: 10_000,
            vestingDurationSeconds: 0,
            cliffSeconds: 0
        });

        params = new HokusaiParams(
            100 ether,
            1_000,
            0,
            bytes32(0),
            "",
            address(this),
            vestingConfig
        );
        token = new HokusaiToken(
            "Echidna Token",
            "ECHT",
            address(this),
            address(params),
            0,
            SUPPLIER_ALLOCATION + INVESTOR_ALLOCATION,
            SUPPLIER_ALLOCATION,
            INVESTOR_ALLOCATION,
            USER_B
        );
        unauthorizedCaller = new EchidnaTokenUnauthorizedCaller();
    }

    function mintInvestorSelf(uint256 amount) external {
        _mintInvestor(address(this), amount);
    }

    function mintInvestorUserA(uint256 amount) external {
        _mintInvestor(USER_A, amount);
    }

    function mintRewardSelf(uint256 amount) external {
        uint256 bounded = _bound(amount, MAX_FUZZ_MINT);
        if (bounded == 0) {
            return;
        }

        try token.mintReward(address(this), bounded) {
            expectedSupply += bounded;
        } catch {}
    }

    function burnSelf(uint256 amount) external {
        uint256 balance = token.balanceOf(address(this));
        uint256 bounded = _bound(amount, balance);
        if (bounded == 0) {
            return;
        }

        try token.burn(bounded) {
            expectedSupply -= bounded;
        } catch {}
    }

    function burnInvestorUserA(uint256 amount) external {
        uint256 available = token.balanceOf(USER_A);
        uint256 remainingInvestor = token.investorMinted();
        if (remainingInvestor < available) {
            available = remainingInvestor;
        }

        uint256 bounded = _bound(amount, available);
        if (bounded == 0) {
            return;
        }

        try token.burnInvestor(USER_A, bounded) {
            expectedSupply -= bounded;
        } catch {}
    }

    function distributeSupplier(uint256 vestedAmount) external {
        if (token.modelSupplierDistributed()) {
            supplierDistributedSeen = true;
            return;
        }

        uint256 bounded = _bound(vestedAmount, token.modelSupplierAllocation());
        try token.distributeModelSupplierAllocation(VESTING_VAULT, bounded) {
            expectedSupply += token.modelSupplierAllocation();
            supplierDistributedSeen = true;
        } catch {}
    }

    function attemptUnauthorizedMint(uint256 amount) external {
        uint256 bounded = _bound(amount, MAX_FUZZ_MINT);
        if (bounded == 0) {
            return;
        }

        if (unauthorizedCaller.tryMintInvestor(token, USER_A, bounded)) {
            unauthorizedMintSucceeded = true;
        }
    }

    function echidna_investor_cap() external view returns (bool) {
        return token.investorMinted() <= token.investorAllocation();
    }

    function echidna_reward_cap() external view returns (bool) {
        return token.rewardMinted() <= token.getRewardMintingCap();
    }

    function echidna_supplier_distributed_once() external view returns (bool) {
        return !supplierDistributedSeen || token.modelSupplierDistributed();
    }

    function echidna_supply_accounting() external view returns (bool) {
        return token.totalSupply() == expectedSupply;
    }

    function echidna_only_controller_can_mint() external view returns (bool) {
        return !unauthorizedMintSucceeded;
    }

    function _mintInvestor(address recipient, uint256 amount) internal {
        uint256 remaining = token.investorAllocation() - token.investorMinted();
        uint256 bounded = _bound(amount, remaining < MAX_FUZZ_MINT ? remaining : MAX_FUZZ_MINT);
        if (bounded == 0) {
            return;
        }

        try token.mintInvestor(recipient, bounded) {
            expectedSupply += bounded;
        } catch {}
    }

    function _bound(uint256 value, uint256 maxValue) internal pure returns (uint256) {
        if (maxValue == 0) {
            return 0;
        }
        return (value % maxValue) + 1;
    }
}
