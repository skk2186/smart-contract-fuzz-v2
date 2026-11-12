// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./interfaces/IHokusaiParams.sol";

/**
 * @title HokusaiParams
 * @dev Implementation of dynamic parameter management for Hokusai tokens
 * Allows governance to adjust key operational parameters without contract upgrades
 */
contract HokusaiParams is IHokusaiParams, AccessControl {
    string private constant TOKENS_PER_DELTA_ONE_BOUNDS_ERROR =
        "tokensPerDeltaOne must be between 100 and 10000000 whole tokens (wei-scaled)";
    uint256 private constant TOKEN_UNIT = 1 ether;
    uint256 private constant MAX_TOKENS_PER_DELTA_ONE_WHOLE = 10_000_000;

    /// @dev Role identifier for governance operations
    bytes32 public constant GOV_ROLE = keccak256("GOV_ROLE");

    /// @dev Minimum allowed value for tokensPerDeltaOne (100 whole tokens, wei-scaled)
    uint256 public constant MIN_TOKENS_PER_DELTA_ONE = 100 ether;

    /// @dev Maximum allowed value for tokensPerDeltaOne (10,000,000 whole tokens, wei-scaled)
    uint256 public constant MAX_TOKENS_PER_DELTA_ONE = 10_000_000 ether;

    /// @dev Minimum allowed value for infrastructureAccrualBps (10% in basis points)
    uint16 public constant MIN_INFRASTRUCTURE_ACCRUAL_BPS = 1000;

    /// @dev Maximum allowed value for infrastructureAccrualBps (100% in basis points)
    uint16 public constant MAX_INFRASTRUCTURE_ACCRUAL_BPS = 10000;

    /// @dev Maximum allowed oracle price per 1000 calls, using the platform's 6-decimal USD convention
    uint256 public constant MAX_ORACLE_PRICE_PER_THOUSAND_USD = 1_000_000_000_000;

    /// @dev Default price epoch duration (30 days in seconds)
    uint256 public constant DEFAULT_PRICE_EPOCH_DURATION = 30 days;

    bool public constant DEFAULT_VESTING_ENABLED = true;
    uint16 public constant DEFAULT_IMMEDIATE_UNLOCK_BPS = 1000;
    uint64 public constant DEFAULT_VESTING_DURATION_SECONDS = 365 days;
    uint64 public constant DEFAULT_CLIFF_SECONDS = 0;

    /// @dev Number of tokens to mint per unit of deltaOne improvement (global default)
    uint256 private _tokensPerDeltaOne;

    /// @dev Metric evaluation mode for this model's token
    IHokusaiParams.MetricType private _metricType;

    /// @dev Infrastructure cost accrual percentage in basis points (global default)
    uint16 private _infrastructureAccrualBps;

    /// @dev Oracle price in USD per 1000 calls (global default)
    uint256 private _oraclePricePerThousandUsd;

    /// @dev Hash of the license reference
    bytes32 private _licenseHash;

    /// @dev URI string for the license reference
    string private _licenseURI;

    /// @dev Vesting policy for contributor rewards minted via TokenManager.
    IHokusaiParams.VestingConfig private _vestingConfig;

    /// @dev Price epoch duration in seconds
    uint256 private _priceEpochDuration;

    /// @dev Struct to track pending parameter updates
    struct PendingUpdate {
        uint256 value;
        uint256 queuedAt;
        bool exists;
    }

    /// @dev Mapping of model ID to epoch start timestamp
    mapping(string => uint256) private _priceEpochStart;

    /// @dev Mapping of model ID to parameter name to pending update
    mapping(string => mapping(string => PendingUpdate)) private _pendingParamUpdates;

    /// @dev Mapping of model ID to model-specific tokensPerDeltaOne
    mapping(string => uint256) private _modelTokensPerDeltaOne;

    /// @dev Mapping of model ID to model-specific infrastructureAccrualBps
    mapping(string => uint16) private _modelInfrastructureAccrualBps;

    /// @dev Mapping to track if a model has been initialized
    mapping(string => bool) private _modelInitialized;

    /**
     * @dev Constructor to initialize the parameter contract
     * @param initialTokensPerDeltaOne Initial tokens per deltaOne value in wei (100-10000000 whole tokens)
     * @param initialInfrastructureAccrualBps Initial infrastructure accrual in basis points (1000-10000)
     * @param initialOraclePricePerThousandUsd Initial oracle price in USD per 1000 calls
     * @param initialLicenseHash Initial license reference hash
     * @param initialLicenseURI Initial license reference URI
     * @param governor Address to grant GOV_ROLE to
     */
    constructor(
        uint256 initialTokensPerDeltaOne,
        uint16 initialInfrastructureAccrualBps,
        uint256 initialOraclePricePerThousandUsd,
        bytes32 initialLicenseHash,
        string memory initialLicenseURI,
        address governor,
        IHokusaiParams.VestingConfig memory initialVestingConfig
    ) {
        require(governor != address(0), "Governor cannot be zero address");
        initialTokensPerDeltaOne = _normalizeTokensPerDeltaOne(initialTokensPerDeltaOne);
        _validateTokensPerDeltaOne(initialTokensPerDeltaOne);
        require(
            initialInfrastructureAccrualBps >= MIN_INFRASTRUCTURE_ACCRUAL_BPS &&
            initialInfrastructureAccrualBps <= MAX_INFRASTRUCTURE_ACCRUAL_BPS,
            "infrastructureAccrualBps must be between 1000 and 10000"
        );
        require(
            initialOraclePricePerThousandUsd <= MAX_ORACLE_PRICE_PER_THOUSAND_USD,
            "oraclePricePerThousandUsd exceeds maximum"
        );

        // Set initial values
        _tokensPerDeltaOne = initialTokensPerDeltaOne;
        _metricType = IHokusaiParams.MetricType.SingleMetric;
        _infrastructureAccrualBps = initialInfrastructureAccrualBps;
        _oraclePricePerThousandUsd = initialOraclePricePerThousandUsd;
        _licenseHash = initialLicenseHash;
        _licenseURI = initialLicenseURI;
        _priceEpochDuration = DEFAULT_PRICE_EPOCH_DURATION;
        _vestingConfig = _resolveInitialVestingConfig(initialVestingConfig);

        // Setup access control
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(GOV_ROLE, governor);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function tokensPerDeltaOne() external view override returns (uint256) {
        return _tokensPerDeltaOne;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function metricType() external view override returns (uint8) {
        return uint8(_metricType);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function infrastructureAccrualBps() external view override returns (uint16) {
        return _infrastructureAccrualBps;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function oraclePricePerThousandUsd() external view override returns (uint256) {
        return _oraclePricePerThousandUsd;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function getProfitShareBps() external view override returns (uint16) {
        return 10000 - _infrastructureAccrualBps;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function licenseHash() external view override returns (bytes32) {
        return _licenseHash;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function licenseURI() external view override returns (string memory) {
        return _licenseURI;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function licenseRef() external view override returns (bytes32 hash, string memory uri) {
        return (_licenseHash, _licenseURI);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function vestingEnabled() external view override returns (bool) {
        return _vestingConfig.enabled;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function immediateUnlockBps() external view override returns (uint16) {
        return _vestingConfig.immediateUnlockBps;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function vestingDurationSeconds() external view override returns (uint64) {
        return _vestingConfig.vestingDurationSeconds;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function cliffSeconds() external view override returns (uint64) {
        return _vestingConfig.cliffSeconds;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function vestingConfig() external view override returns (IHokusaiParams.VestingConfig memory) {
        return _vestingConfig;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setTokensPerDeltaOne(uint256 newValue) external override onlyRole(GOV_ROLE) {
        newValue = _normalizeTokensPerDeltaOne(newValue);
        _validateTokensPerDeltaOne(newValue);

        uint256 oldValue = _tokensPerDeltaOne;
        _tokensPerDeltaOne = newValue;

        emit TokensPerDeltaOneSet(oldValue, newValue, msg.sender);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setMetricType(uint8 newMetricType) external override onlyRole(GOV_ROLE) {
        require(newMetricType <= uint8(IHokusaiParams.MetricType.SingleMetric), "Invalid metric type");

        uint8 oldMetricType = uint8(_metricType);
        _metricType = IHokusaiParams.MetricType(newMetricType);

        emit MetricTypeSet(oldMetricType, newMetricType, msg.sender);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setInfrastructureAccrualBps(uint16 newBps) external override onlyRole(GOV_ROLE) {
        require(
            newBps >= MIN_INFRASTRUCTURE_ACCRUAL_BPS && newBps <= MAX_INFRASTRUCTURE_ACCRUAL_BPS,
            "infrastructureAccrualBps must be between 1000 and 10000"
        );

        uint16 oldBps = _infrastructureAccrualBps;
        _infrastructureAccrualBps = newBps;

        emit InfrastructureAccrualBpsSet(oldBps, newBps, msg.sender);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setOraclePricePerThousandUsd(uint256 newValue) external override onlyRole(GOV_ROLE) {
        require(
            newValue <= MAX_ORACLE_PRICE_PER_THOUSAND_USD,
            "oraclePricePerThousandUsd exceeds maximum"
        );

        uint256 oldValue = _oraclePricePerThousandUsd;
        _oraclePricePerThousandUsd = newValue;

        emit OraclePricePerThousandUsdSet(oldValue, newValue, msg.sender);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setLicenseRef(bytes32 hash, string memory uri) external override onlyRole(GOV_ROLE) {
        bytes32 oldHash = _licenseHash;
        _licenseHash = hash;
        _licenseURI = uri;

        emit LicenseRefSet(oldHash, hash, uri, msg.sender);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function setVestingConfig(IHokusaiParams.VestingConfig calldata cfg) external override onlyRole(GOV_ROLE) {
        _setVestingConfig(cfg);
    }

    // ============================================================
    // EPOCH-BASED PRICE LOCKING FUNCTIONS
    // ============================================================

    /**
     * @dev Initializes a model with current global defaults if not already initialized
     * @param modelId The model identifier
     */
    function _initializeModelIfNeeded(string memory modelId) private {
        if (!_modelInitialized[modelId]) {
            _modelTokensPerDeltaOne[modelId] = _tokensPerDeltaOne;
            _modelInfrastructureAccrualBps[modelId] = _infrastructureAccrualBps;
            _priceEpochStart[modelId] = block.timestamp;
            _modelInitialized[modelId] = true;
        }
    }

    /**
     * @dev Normalizes and validates a parameter value before it is stored.
     */
    function _normalizeTokensPerDeltaOne(uint256 value) private pure returns (uint256) {
        if (value <= MAX_TOKENS_PER_DELTA_ONE_WHOLE) {
            return value * TOKEN_UNIT;
        }
        return value;
    }

    function _resolveInitialVestingConfig(
        IHokusaiParams.VestingConfig memory cfg
    ) private pure returns (IHokusaiParams.VestingConfig memory resolved) {
        if (_isDefaultVestingSentinel(cfg)) {
            return IHokusaiParams.VestingConfig({
                enabled: DEFAULT_VESTING_ENABLED,
                immediateUnlockBps: DEFAULT_IMMEDIATE_UNLOCK_BPS,
                vestingDurationSeconds: DEFAULT_VESTING_DURATION_SECONDS,
                cliffSeconds: DEFAULT_CLIFF_SECONDS
            });
        }

        _validateVestingConfig(cfg);
        return cfg;
    }

    function _isDefaultVestingSentinel(IHokusaiParams.VestingConfig memory cfg) private pure returns (bool) {
        return
            !cfg.enabled &&
            cfg.immediateUnlockBps == 0 &&
            cfg.vestingDurationSeconds == 0 &&
            cfg.cliffSeconds == 0;
    }

    function _validateVestingConfig(IHokusaiParams.VestingConfig memory cfg) private pure {
        require(cfg.immediateUnlockBps <= 10000, "immediateUnlockBps must be <= 10000");

        if (cfg.enabled) {
            require(cfg.vestingDurationSeconds > 0, "vesting duration must be > 0");
            require(cfg.cliffSeconds <= cfg.vestingDurationSeconds, "cliff exceeds vesting duration");
        } else {
            require(cfg.cliffSeconds == 0, "disabled vesting cliff must be 0");
            require(cfg.vestingDurationSeconds == 0, "disabled vesting duration must be 0");
        }
    }

    function _setVestingConfig(IHokusaiParams.VestingConfig memory cfg) private {
        _validateVestingConfig(cfg);
        _vestingConfig = cfg;

        emit VestingConfigSet(
            cfg.enabled,
            cfg.immediateUnlockBps,
            cfg.vestingDurationSeconds,
            cfg.cliffSeconds,
            msg.sender
        );
    }

    function _validateTokensPerDeltaOne(uint256 value) private pure {
        require(
            value >= MIN_TOKENS_PER_DELTA_ONE && value <= MAX_TOKENS_PER_DELTA_ONE,
            TOKENS_PER_DELTA_ONE_BOUNDS_ERROR
        );
    }

    /**
     * @dev Validates parameter name and value and returns the normalized stored value.
     * @param paramName The parameter name
     * @param newValue The new value to validate
     */
    function _validateParam(string memory paramName, uint256 newValue) private pure returns (uint256 normalizedValue) {
        bytes32 paramHash = keccak256(bytes(paramName));

        if (paramHash == keccak256(bytes("tokensPerDeltaOne"))) {
            normalizedValue = _normalizeTokensPerDeltaOne(newValue);
            _validateTokensPerDeltaOne(normalizedValue);
        } else if (paramHash == keccak256(bytes("infrastructureAccrualBps"))) {
            require(
                newValue >= MIN_INFRASTRUCTURE_ACCRUAL_BPS && newValue <= MAX_INFRASTRUCTURE_ACCRUAL_BPS,
                "infrastructureAccrualBps must be between 1000 and 10000"
            );
            normalizedValue = newValue;
        } else {
            revert("Invalid parameter name");
        }
    }

    /**
     * @dev Gets the current value of a parameter for a model
     * @param modelId The model identifier
     * @param paramName The parameter name
     * @return The current parameter value
     */
    function _getCurrentParamValue(string memory modelId, string memory paramName) private view returns (uint256) {
        bytes32 paramHash = keccak256(bytes(paramName));

        if (paramHash == keccak256(bytes("tokensPerDeltaOne"))) {
            return _modelInitialized[modelId] ? _modelTokensPerDeltaOne[modelId] : _tokensPerDeltaOne;
        } else if (paramHash == keccak256(bytes("infrastructureAccrualBps"))) {
            return _modelInitialized[modelId] ? _modelInfrastructureAccrualBps[modelId] : _infrastructureAccrualBps;
        }
        revert("Invalid parameter name");
    }

    /**
     * @dev Sets a parameter value for a model
     * @param modelId The model identifier
     * @param paramName The parameter name
     * @param newValue The new value
     */
    function _setParamValue(string memory modelId, string memory paramName, uint256 newValue) private {
        bytes32 paramHash = keccak256(bytes(paramName));

        if (paramHash == keccak256(bytes("tokensPerDeltaOne"))) {
            _modelTokensPerDeltaOne[modelId] = newValue;
        } else if (paramHash == keccak256(bytes("infrastructureAccrualBps"))) {
            _modelInfrastructureAccrualBps[modelId] = uint16(newValue);
        }
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function queueParamUpdate(
        string memory modelId,
        string memory paramName,
        uint256 newValue
    ) external override onlyRole(GOV_ROLE) {
        require(bytes(modelId).length > 0, "Model ID cannot be empty");

        _initializeModelIfNeeded(modelId);
        uint256 normalizedValue = _validateParam(paramName, newValue);

        uint256 currentValue = _getCurrentParamValue(modelId, paramName);
        uint256 effectiveAfter = _priceEpochStart[modelId] + _priceEpochDuration;

        _pendingParamUpdates[modelId][paramName] = PendingUpdate({
            value: normalizedValue,
            queuedAt: block.timestamp,
            exists: true
        });

        emit ParamUpdateQueued(modelId, paramName, currentValue, normalizedValue, effectiveAfter);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function applyPendingUpdates(string memory modelId) external override {
        require(bytes(modelId).length > 0, "Model ID cannot be empty");
        require(_modelInitialized[modelId], "Model not initialized");

        uint256 epochEnd = _priceEpochStart[modelId] + _priceEpochDuration;
        require(block.timestamp >= epochEnd, "Epoch has not ended yet");

        // Apply tokensPerDeltaOne if pending
        string memory tokensParam = "tokensPerDeltaOne";
        if (_pendingParamUpdates[modelId][tokensParam].exists) {
            uint256 oldValue = _modelTokensPerDeltaOne[modelId];
            uint256 newValue = _pendingParamUpdates[modelId][tokensParam].value;
            _modelTokensPerDeltaOne[modelId] = newValue;
            delete _pendingParamUpdates[modelId][tokensParam];
            emit ParamUpdateApplied(modelId, tokensParam, oldValue, newValue);
        }

        // Apply infrastructureAccrualBps if pending
        string memory infraParam = "infrastructureAccrualBps";
        if (_pendingParamUpdates[modelId][infraParam].exists) {
            uint256 oldValue = _modelInfrastructureAccrualBps[modelId];
            uint256 newValue = _pendingParamUpdates[modelId][infraParam].value;
            _modelInfrastructureAccrualBps[modelId] = uint16(newValue);
            delete _pendingParamUpdates[modelId][infraParam];
            emit ParamUpdateApplied(modelId, infraParam, oldValue, newValue);
        }

        // Start new epoch
        _priceEpochStart[modelId] = block.timestamp;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function getPriceEpochInfo(string memory modelId) external view override returns (
        uint256 epochStart,
        uint256 epochEnd,
        bool hasPendingUpdates
    ) {
        if (!_modelInitialized[modelId]) {
            return (0, 0, false);
        }

        epochStart = _priceEpochStart[modelId];
        epochEnd = epochStart + _priceEpochDuration;

        hasPendingUpdates =
            _pendingParamUpdates[modelId]["tokensPerDeltaOne"].exists ||
            _pendingParamUpdates[modelId]["infrastructureAccrualBps"].exists;

        return (epochStart, epochEnd, hasPendingUpdates);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function cancelPendingUpdate(
        string memory modelId,
        string memory paramName
    ) external override onlyRole(GOV_ROLE) {
        require(bytes(modelId).length > 0, "Model ID cannot be empty");
        require(_pendingParamUpdates[modelId][paramName].exists, "No pending update for this parameter");

        delete _pendingParamUpdates[modelId][paramName];
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function emergencySetParam(
        string memory modelId,
        string memory paramName,
        uint256 newValue,
        string memory reason
    ) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        require(bytes(modelId).length > 0, "Model ID cannot be empty");
        require(bytes(reason).length > 0, "Reason cannot be empty");

        _initializeModelIfNeeded(modelId);
        uint256 normalizedValue = _validateParam(paramName, newValue);
        _setParamValue(modelId, paramName, normalizedValue);

        // Clear any pending update for this parameter
        if (_pendingParamUpdates[modelId][paramName].exists) {
            delete _pendingParamUpdates[modelId][paramName];
        }

        emit EmergencyParamOverride(modelId, paramName, normalizedValue, reason);
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function priceEpochDuration() external view override returns (uint256) {
        return _priceEpochDuration;
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function getEpochStart(string memory modelId) external view override returns (uint256) {
        return _priceEpochStart[modelId];
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function getModelTokensPerDeltaOne(string memory modelId) external view override returns (uint256) {
        if (!_modelInitialized[modelId]) {
            return _tokensPerDeltaOne;
        }
        return _modelTokensPerDeltaOne[modelId];
    }

    /**
     * @inheritdoc IHokusaiParams
     */
    function getModelInfrastructureAccrualBps(string memory modelId) external view override returns (uint16) {
        if (!_modelInitialized[modelId]) {
            return _infrastructureAccrualBps;
        }
        return _modelInfrastructureAccrualBps[modelId];
    }
}
