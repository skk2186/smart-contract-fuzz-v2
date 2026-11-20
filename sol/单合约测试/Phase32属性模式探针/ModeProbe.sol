// Phase32 最小属性模式探针。只用于测试 Echidna 2.3.2 的模式接入，不属于 V2 种子或算法输入。
pragma solidity 0.4.25;

contract BooleanModeProbe {
    uint256 public counter;

    function increment() external {
        counter += 1;
    }

    function ordinaryRevert() external pure {
        require(false, "ordinary transaction revert");
    }

    function echidna_counter_at_most_one() external view returns (bool) {
        return counter <= 1;
    }
}

contract AssertionModeProbe {
    uint256 public counter;

    function incrementAndCheck() external {
        counter += 1;
        assert(counter < 2);
    }

    function ordinaryRevert() external pure {
        revert("ordinary transaction revert");
    }
}

contract RevertOnlyModeProbe {
    function ordinaryRevert() external pure {
        require(false, "ordinary transaction revert");
    }
}

contract MultipleAssertionModeProbe {
    uint256 public counter;

    function targetCheck() external {
        counter += 1;
        assert(counter < 2);
    }

    function unrelatedCheck() external pure {
        assert(false);
    }
}

contract FoundryModeProbe {
    bool public IS_TEST = true;
    uint256 public counter;

    function setUp() public {
        counter = 0;
    }

    function increment() external {
        counter += 1;
    }

    function test_counter_stays_below_two(uint256 value) public {
        counter = value;
        assert(counter < 2);
    }

    function testFail_expected_revert() public pure {
        revert("expected Foundry test failure");
    }
}
