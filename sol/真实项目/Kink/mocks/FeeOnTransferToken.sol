// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title FeeOnTransferToken
 * @notice ERC20 that burns a configurable percentage on every transfer
 */
contract FeeOnTransferToken is ERC20 {
    uint256 public immutable feeBps;
    uint256 public totalBurned;

    constructor(string memory name_, string memory symbol_, uint256 _feeBps) ERC20(name_, symbol_) {
        require(_feeBps <= 500, "FeeTooHigh");
        feeBps = _feeBps;
        _mint(msg.sender, 1_000_000 * 1e18);
    }

    function _update(address from, address to, uint256 value) internal override {
        if (feeBps == 0 || from == address(0) || to == address(0) || value == 0) {
            super._update(from, to, value);
            return;
        }

        uint256 fee = (value * feeBps) / 10_000;
        uint256 amountAfterFee = value - fee;

        if (fee > 0) {
            super._update(from, address(0), fee);
            totalBurned += fee;
        }

        super._update(from, to, amountAfterFee);
    }
}

