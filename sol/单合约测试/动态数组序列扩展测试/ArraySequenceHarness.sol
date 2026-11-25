pragma solidity 0.8.26;

/// @notice Isolated native-corpus fixture for signed and unsigned ABI arrays.
contract ArraySequenceHarness {
    bool public reached;

    function consume(int8[] calldata signedValues,
                     uint256[] calldata unsignedValues) external {
        if (signedValues.length < 2 || unsignedValues.length < 1) return;
        if (signedValues[0] == -3 && signedValues[1] == 2 && unsignedValues[0] == 7) {
            reached = true;
        }
    }

    function echidna_array_input_replays() external view returns (bool) {
        return !reached;
    }
}
