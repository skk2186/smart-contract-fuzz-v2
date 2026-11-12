// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/proxy/Clones.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./KinkPool.sol";
import "./PoolRegistry.sol";

/**
 * @title KinkFactory
 * @notice Factory for creating KinkPool instances using minimal proxy pattern
 */
contract KinkFactory is Ownable {
    using Clones for address;

    /// @notice Implementation contract address
    address public immutable implementation;

    /// @notice Array of all created pools
    address[] public allPools;

    /// @notice Mapping from token pair to pool address
    mapping(address => mapping(address => address[])) public getPools;
    mapping(bytes32 => address) public getPool;
    mapping(address => bool) public isPool;

    /// @notice Protocol fee configuration
    address public feeReceiver;
    uint256 public baseFeeShare;
    uint256 public kinkingFeeShare;
    uint256 public constant MAX_FEE_SHARE = 5000; // 50%

    PoolRegistry public immutable registry;

    event PoolCreated(
        address indexed token0,
        address indexed token1,
        address indexed pool,
        uint256 A0,
        uint256 A1,
        uint256 baseFee,
        uint256 kinkingFee,
        uint256 softPeg0,
        uint256 softPeg1
    );

    event ProtocolFeesUpdated(
        address indexed feeReceiver,
        uint256 baseFeeShare,
        uint256 kinkingFeeShare
    );

    constructor(address _registry) Ownable(msg.sender) {
        // Deploy standalone implementation that clones can initialize
        implementation = address(new KinkPool());
        registry = PoolRegistry(_registry);
    }

    /**
     * @notice Update protocol fee configuration
     * @param _feeReceiver Address to receive protocol fees
     * @param _baseFeeShare Admin share of base fee in bps
     * @param _kinkingFeeShare Admin share of kinking fee in bps
     */
    function setProtocolFees(
        address _feeReceiver,
        uint256 _baseFeeShare,
        uint256 _kinkingFeeShare
    ) external onlyOwner {
        require(_baseFeeShare <= MAX_FEE_SHARE, "KinkFactory: Fee share too high");
        require(_kinkingFeeShare <= MAX_FEE_SHARE, "KinkFactory: Fee share too high");
        require(_feeReceiver != address(0) || (_baseFeeShare == 0 && _kinkingFeeShare == 0), "KinkFactory: Zero address receiver");

        feeReceiver = _feeReceiver;
        baseFeeShare = _baseFeeShare;
        kinkingFeeShare = _kinkingFeeShare;

        emit ProtocolFeesUpdated(_feeReceiver, _baseFeeShare, _kinkingFeeShare);
    }

    /**
     * @notice Get the number of pools created
     * @return Number of pools
     */
    function allPoolsLength() external view returns (uint256) {
        return allPools.length;
    }

    /**
     * @notice Create a new pool
     * @param tokenA Address of first token
     * @param tokenB Address of second token
     * @param _A0 Amplification when tokenA > tokenB
     * @param _A1 Amplification when tokenB > tokenA
     * @param _baseFee Base fee in basis points
     * @param _kinkingFee Kinking fee in basis points
     * @param _softPeg0 Soft peg price threshold for token0 (when selling token0)
     * @param _softPeg1 Soft peg price threshold for token1 (when selling token1)
     * @return pool Address of the created pool
     */
    function createPool(
        address tokenA,
        address tokenB,
        uint256 _A0,
        uint256 _A1,
        uint256 _baseFee,
        uint256 _kinkingFee,
        uint256 _softPeg0,
        uint256 _softPeg1
    )
        external
        returns (address pool)
    {
        require(tokenA != tokenB, "KinkFactory: Identical tokens");
        require(tokenA != address(0) && tokenB != address(0), "KinkFactory: Zero address");

        // Sort tokens and align amplification parameters to the deployed ordering
        // Note: _softPeg0 corresponds to tokenA, _softPeg1 corresponds to tokenB
        (address token0, address token1, uint256 A0Param, uint256 A1Param, uint256 peg0, uint256 peg1) =
            tokenA < tokenB
                ? (tokenA, tokenB, _A0, _A1, _softPeg0, _softPeg1)
                : (tokenB, tokenA, _A1, _A0, _softPeg1, _softPeg0);

        // Hash must include new fee shares to ensure uniqueness if they differ
        bytes32 paramsHash = keccak256(abi.encodePacked(token0, token1, A0Param, A1Param, _baseFee, _kinkingFee, peg0, peg1));
        require(getPool[paramsHash] == address(0), "KinkFactory: Pool exists");

        // Clone implementation
        pool = implementation.clone();

        // Update state variables BEFORE initializing
        getPool[paramsHash] = pool;
        getPools[token0][token1].push(pool);
        getPools[token1][token0].push(pool); // Reverse mapping
        allPools.push(pool);
        isPool[pool] = true;

        // Initialize pool
        // Pass msg.sender as admin (or factory could be admin if desired, but user usually wants control)
        // Here we set msg.sender (the deployer) as the admin.
        KinkPool(pool).initialize(token0, token1, A0Param, A1Param, _baseFee, _kinkingFee, peg0, peg1, msg.sender);

        registry.registerPool(token0, token1, pool);

        emit PoolCreated(token0, token1, pool, A0Param, A1Param, _baseFee, _kinkingFee, peg0, peg1);
    }

    /**
     * @notice Get pool for specific parameters
     */
    function getPoolByParams(
        address tokenA,
        address tokenB,
        uint256 _A0,
        uint256 _A1,
        uint256 _baseFee,
        uint256 _kinkingFee,
        uint256 _softPeg0,
        uint256 _softPeg1
    ) external view returns (address) {
        (address token0, address token1, uint256 A0Param, uint256 A1Param, uint256 peg0, uint256 peg1) =
            tokenA < tokenB
                ? (tokenA, tokenB, _A0, _A1, _softPeg0, _softPeg1)
                : (tokenB, tokenA, _A1, _A0, _softPeg1, _softPeg0);

        bytes32 paramsHash = keccak256(abi.encodePacked(token0, token1, A0Param, A1Param, _baseFee, _kinkingFee, peg0, peg1));
        return getPool[paramsHash];
    }

    /**
     * @notice Get all pools for a pair
     */
    function getPoolsForPair(address tokenA, address tokenB) external view returns (address[] memory) {
        return getPools[tokenA][tokenB];
    }
}
