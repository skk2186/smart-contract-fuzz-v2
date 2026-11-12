// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title IHokusaiParams
 * @dev Interface for Hokusai token parameter management
 * Provides a standardized way to manage dynamic parameters for token operations
 * without requiring contract upgrades.
 */
interface IHokusaiParams {
    enum MetricType {
        SingleMetric
    }

    struct VestingConfig {
        bool enabled;
        uint16 immediateUnlockBps;
        uint64 vestingDurationSeconds;
        uint64 cliffSeconds;
    }

    /**
     * @dev Returns the metric evaluation mode for the model's token
     * @return The metric type enum value (0 = single-metric)
     */
    function metricType() external view returns (uint8);

    /**
     * @dev Returns the number of tokens to mint per unit of deltaOne improvement
     * @return The tokens per deltaOne value (replaces hardcoded baseRewardRate)
     */
    function tokensPerDeltaOne() external view returns (uint256);

    /**
     * @dev Returns the infrastructure cost accrual percentage in basis points
     * @return The accrual percentage (5000-10000 basis points, where 5000 = 50%, 10000 = 100%)
     */
    function infrastructureAccrualBps() external view returns (uint16);

    /**
     * @dev Returns the oracle price in USD per 1000 calls
     * @return The oracle price, using the platform's USD decimal convention
     */
    function oraclePricePerThousandUsd() external view returns (uint256);

    /**
     * @dev Returns the profit share percentage in basis points (residual after infrastructure)
     * @return The profit share percentage (calculated as 10000 - infrastructureAccrualBps)
     */
    function getProfitShareBps() external view returns (uint16);

    /**
     * @dev Returns the license reference hash
     * @return The bytes32 hash of the license reference
     */
    function licenseHash() external view returns (bytes32);

    /**
     * @dev Returns the license reference URI
     * @return The string URI for the license reference
     */
    function licenseURI() external view returns (string memory);

    /**
     * @dev Returns both license hash and URI in a single call for gas efficiency
     * @return hash The bytes32 hash of the license reference
     * @return uri The string URI for the license reference
     */
    function licenseRef() external view returns (bytes32 hash, string memory uri);

    /**
     * @dev Returns whether reward vesting is enabled for contributor emissions.
     */
    function vestingEnabled() external view returns (bool);

    /**
     * @dev Returns the liquid reward portion in basis points.
     */
    function immediateUnlockBps() external view returns (uint16);

    /**
     * @dev Returns the full vesting duration in seconds.
     */
    function vestingDurationSeconds() external view returns (uint64);

    /**
     * @dev Returns the cliff in seconds before any tokens become claimable.
     */
    function cliffSeconds() external view returns (uint64);

    /**
     * @dev Returns the full vesting configuration.
     */
    function vestingConfig() external view returns (VestingConfig memory);

    /**
     * @dev Sets the tokens per deltaOne parameter
     * @param newValue The new tokens per deltaOne value (must be between 100-100000)
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     * - newValue must be within valid bounds (100-100000)
     */
    function setTokensPerDeltaOne(uint256 newValue) external;

    /**
     * @dev Sets the metric evaluation mode
     * @param newMetricType The metric type enum value (0 = single-metric)
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     * - newMetricType must be a supported mode
     */
    function setMetricType(uint8 newMetricType) external;

    /**
     * @dev Sets the infrastructure cost accrual percentage
     * @param newBps The new accrual in basis points (must be 5000-10000, i.e., 50-100%)
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     * - newBps must be between 5000 and 10000 (50-100%)
     */
    function setInfrastructureAccrualBps(uint16 newBps) external;

    /**
     * @dev Sets the oracle price in USD per 1000 calls
     * @param newValue The new oracle price using the platform's USD decimal convention
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     * - newValue must not exceed the implementation's sanity bound
     */
    function setOraclePricePerThousandUsd(uint256 newValue) external;

    /**
     * @dev Sets the license reference
     * @param hash The bytes32 hash of the license reference
     * @param uri The string URI for the license reference
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     */
    function setLicenseRef(bytes32 hash, string memory uri) external;

    /**
     * @dev Sets the vesting configuration for contributor rewards.
     */
    function setVestingConfig(VestingConfig calldata cfg) external;

    /**
     * @dev Emitted when tokensPerDeltaOne is updated
     * @param oldValue The previous tokens per deltaOne value
     * @param newValue The new tokens per deltaOne value
     * @param updatedBy The address that made the update
     */
    event TokensPerDeltaOneSet(uint256 indexed oldValue, uint256 indexed newValue, address indexed updatedBy);

    /**
     * @dev Emitted when metricType is updated
     * @param oldMetricType The previous metric type
     * @param newMetricType The new metric type
     * @param updatedBy The address that made the update
     */
    event MetricTypeSet(uint8 indexed oldMetricType, uint8 indexed newMetricType, address indexed updatedBy);

    /**
     * @dev Emitted when infrastructureAccrualBps is updated
     * @param oldBps The previous accrual in basis points
     * @param newBps The new accrual in basis points
     * @param updatedBy The address that made the update
     */
    event InfrastructureAccrualBpsSet(uint16 indexed oldBps, uint16 indexed newBps, address indexed updatedBy);

    /**
     * @dev Emitted when oraclePricePerThousandUsd is updated
     * @param oldValue The previous oracle price value
     * @param newValue The new oracle price value
     * @param updatedBy The address that made the update
     */
    event OraclePricePerThousandUsdSet(
        uint256 indexed oldValue,
        uint256 indexed newValue,
        address indexed updatedBy
    );

    /**
     * @dev Emitted when license reference is updated
     * @param oldHash The previous license hash
     * @param newHash The new license hash
     * @param newUri The new license URI
     * @param updatedBy The address that made the update
     */
    event LicenseRefSet(bytes32 indexed oldHash, bytes32 indexed newHash, string newUri, address indexed updatedBy);

    /**
     * @dev Emitted when the vesting configuration is updated.
     */
    event VestingConfigSet(
        bool enabled,
        uint16 immediateUnlockBps,
        uint64 vestingDurationSeconds,
        uint64 cliffSeconds,
        address indexed updatedBy
    );

    /**
     * @dev Emitted when a parameter update is queued for a model
     * @param modelId The model identifier
     * @param paramName The parameter name being updated
     * @param currentValue The current parameter value
     * @param newValue The new parameter value
     * @param effectiveAfter Timestamp when the update can be applied
     */
    event ParamUpdateQueued(
        string indexed modelId,
        string paramName,
        uint256 currentValue,
        uint256 newValue,
        uint256 effectiveAfter
    );

    /**
     * @dev Emitted when a queued parameter update is applied
     * @param modelId The model identifier
     * @param paramName The parameter name being updated
     * @param oldValue The previous parameter value
     * @param newValue The new parameter value
     */
    event ParamUpdateApplied(
        string indexed modelId,
        string paramName,
        uint256 oldValue,
        uint256 newValue
    );

    /**
     * @dev Emitted when an emergency parameter override is performed
     * @param modelId The model identifier
     * @param paramName The parameter name being overridden
     * @param value The new parameter value
     * @param reason The reason for emergency override
     */
    event EmergencyParamOverride(
        string indexed modelId,
        string paramName,
        uint256 value,
        string reason
    );

    /**
     * @dev Queues a parameter update for a model
     * @param modelId The model identifier
     * @param paramName The parameter name ("tokensPerDeltaOne" or "infrastructureAccrualBps")
     * @param newValue The new parameter value
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     * - paramName must be valid
     * - newValue must be within valid bounds
     */
    function queueParamUpdate(string memory modelId, string memory paramName, uint256 newValue) external;

    /**
     * @dev Applies all pending parameter updates for a model if epoch boundary has passed
     * @param modelId The model identifier
     * Requirements:
     * - Permissionless function (anyone can call)
     * - Can only apply updates after epoch boundary
     */
    function applyPendingUpdates(string memory modelId) external;

    /**
     * @dev Gets the price epoch information for a model
     * @param modelId The model identifier
     * @return epochStart Timestamp when current epoch started
     * @return epochEnd Timestamp when current epoch ends
     * @return hasPendingUpdates Whether there are pending parameter updates
     */
    function getPriceEpochInfo(string memory modelId) external view returns (
        uint256 epochStart,
        uint256 epochEnd,
        bool hasPendingUpdates
    );

    /**
     * @dev Cancels a pending parameter update for a model
     * @param modelId The model identifier
     * @param paramName The parameter name to cancel
     * Requirements:
     * - Only addresses with GOV_ROLE can call this function
     */
    function cancelPendingUpdate(string memory modelId, string memory paramName) external;

    /**
     * @dev Emergency override to force-apply a parameter change bypassing epoch
     * @param modelId The model identifier
     * @param paramName The parameter name
     * @param newValue The new parameter value
     * @param reason The reason for emergency override
     * Requirements:
     * - Only addresses with DEFAULT_ADMIN_ROLE can call this function
     * - Should only be used in emergencies
     */
    function emergencySetParam(
        string memory modelId,
        string memory paramName,
        uint256 newValue,
        string memory reason
    ) external;

    /**
     * @dev Gets the price epoch duration
     * @return The epoch duration in seconds
     */
    function priceEpochDuration() external view returns (uint256);

    /**
     * @dev Gets the epoch start time for a model
     * @param modelId The model identifier
     * @return The epoch start timestamp
     */
    function getEpochStart(string memory modelId) external view returns (uint256);

    /**
     * @dev Gets model-specific tokensPerDeltaOne parameter
     * @param modelId The model identifier
     * @return The tokens per deltaOne value for the model
     */
    function getModelTokensPerDeltaOne(string memory modelId) external view returns (uint256);

    /**
     * @dev Gets model-specific infrastructureAccrualBps parameter
     * @param modelId The model identifier
     * @return The infrastructure accrual in basis points for the model
     */
    function getModelInfrastructureAccrualBps(string memory modelId) external view returns (uint16);
}
