pragma solidity 0.4.25;

/**
 * Upstream source: SmartBugs Curated (CVE-2018-10299 / BECToken batchTransfer)
 * Repository: https://github.com/smartbugs/smartbugs-curated
 * License: MIT
 *
 * batchTransfer() computes amount = uint256(cnt) * _value without overflow check,
 * allowing an attacker with 0 balance to mint massive tokens to multiple receivers
 * when cnt * _value overflows to 0.
 */
contract SmartBugsBECTokenHarness {
    uint256 public totalSupply;
    mapping(address => uint256) public balances;
    address public constant PLAYER1 = 0x0000000000000000000000000000000000010000;
    address public constant PLAYER2 = 0x0000000000000000000000000000000000020000;
    address public constant PLAYER3 = 0x0000000000000000000000000000000000030000;

    event Transfer(address indexed from, address indexed to, uint256 value);

    constructor() public {
        totalSupply = 1000000;
        balances[PLAYER1] = totalSupply;
        emit Transfer(address(0), PLAYER1, totalSupply);
    }

    function transfer(address _to, uint256 _value) public returns (bool) {
        require(_to != address(0));
        require(_value > 0 && _value <= balances[msg.sender]);
        require(balances[_to] + _value >= balances[_to]);
        balances[msg.sender] -= _value;
        balances[_to] += _value;
        emit Transfer(msg.sender, _to, _value);
        return true;
    }

    function batchTransfer(address[] _receivers, uint256 _value) public returns (bool) {
        uint256 cnt = _receivers.length;
        uint256 amount = uint256(cnt) * _value;
        require(cnt > 0 && cnt <= 20);
        require(_value > 0 && balances[msg.sender] >= amount);

        balances[msg.sender] -= amount;
        for (uint256 i = 0; i < cnt; i++) {
            require(_receivers[i] != address(0));
            balances[_receivers[i]] += _value;
            emit Transfer(msg.sender, _receivers[i], _value);
        }
        return true;
    }

    /// @notice Conservation invariant: sum of tracked accounts must never exceed totalSupply.
    function echidna_supply_conserved() public view returns (bool) {
        return balances[PLAYER1] <= totalSupply &&
               balances[PLAYER2] <= totalSupply &&
               balances[PLAYER3] <= totalSupply;
    }
}
