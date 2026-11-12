// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

contract PoolRegistry is Ownable {
    event PoolRegistered(address indexed token0, address indexed token1, address indexed pool);
    event FactoryUpdated(address indexed oldFactory, address indexed newFactory);

    address[] public allPools;
    mapping(address => bool) public isPool;
    mapping(bytes32 => address[]) private poolsByPair;
    address public canonicalFactory;

    constructor(address initialOwner, address initialFactory) Ownable(initialOwner) {
        canonicalFactory = initialFactory;
    }

    function setFactory(address newFactory) external onlyOwner {
        require(newFactory != address(0), "PoolRegistry: zero factory");
        emit FactoryUpdated(canonicalFactory, newFactory);
        canonicalFactory = newFactory;
    }

    function registerPool(address token0, address token1, address pool) external {
        require(msg.sender == canonicalFactory, "PoolRegistry: only factory");
        require(!isPool[pool], "PoolRegistry: Pool already registered");
        require(pool != address(0), "PoolRegistry: Zero pool");

        isPool[pool] = true;
        allPools.push(pool);

        (address ordered0, address ordered1) = token0 < token1 ? (token0, token1) : (token1, token0);
        poolsByPair[keccak256(abi.encodePacked(ordered0, ordered1))].push(pool);

        emit PoolRegistered(ordered0, ordered1, pool);
    }

    function allPoolsLength() external view returns (uint256) {
        return allPools.length;
    }

    function getPoolsForPair(address tokenA, address tokenB) external view returns (address[] memory) {
        (address ordered0, address ordered1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        return poolsByPair[keccak256(abi.encodePacked(ordered0, ordered1))];
    }
}

