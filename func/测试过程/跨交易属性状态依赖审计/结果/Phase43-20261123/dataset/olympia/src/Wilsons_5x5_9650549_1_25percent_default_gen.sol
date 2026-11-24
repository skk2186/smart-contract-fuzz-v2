pragma solidity 0.8.26;
contract Maze { 
	bool public bug = false;
	bool private stop = false;
	int64 next_cell = 0;
	function func_start(int8[] memory inp) internal {}
	function func_bug(int8[] memory inp) internal {
		bug = true;
		return;
	}
	function func_0(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = -2;
		}
		else if (inp[0] < 42) {
			next_cell = 5;
		}
		else if (inp[0] >= 42) {
			next_cell = 1;
		}
		else {
			stop = true;
		}
	}
	}
	function func_1(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 6;
		}
		else if (inp[0] >= 0) {
			next_cell = 2;
		}
		else {
			stop = true;
		}
	}
	}
	function func_2(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_3(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 8;
		}
		else if (inp[0] >= 0) {
			next_cell = 4;
		}
		else {
			stop = true;
		}
	}
	}
	function func_4(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 9;
		}
		else {
			stop = true;
		}
	}
	}
	function func_5(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 0;
		}
		else if (inp[0] >= 0) {
			next_cell = 10;
		}
		else {
			stop = true;
		}
	}
	}
	function func_6(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_7(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 8;
		}
		else {
			stop = true;
		}
	}
	}
	function func_8(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 3;
		}
		else if (inp[0] >= 0) {
			next_cell = 7;
		}
		else {
			stop = true;
		}
	}
	}
	function func_9(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 4;
		}
		else if (inp[0] >= 0) {
			next_cell = 14;
		}
		else {
			stop = true;
		}
	}
	}
	function func_10(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 11;
		}
		else {
			stop = true;
		}
	}
	}
	function func_11(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 16;
		}
		else {
			stop = true;
		}
	}
	}
	function func_12(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 7;
		}
		else if (inp[0] < 42) {
			next_cell = 17;
		}
		else if (inp[0] >= 42) {
			next_cell = 13;
		}
		else {
			stop = true;
		}
	}
	}
	function func_13(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_14(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 19;
		}
		else {
			stop = true;
		}
	}
	}
	function func_15(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_16(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 15;
		}
		else if (inp[0] < 42) {
			next_cell = 21;
		}
		else if (inp[0] >= 42) {
			next_cell = 17;
		}
		else {
			stop = true;
		}
	}
	}
	function func_17(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 12;
		}
		else if (inp[0] >= 0) {
			next_cell = 22;
		}
		else {
			stop = true;
		}
	}
	}
	function func_18(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 23;
		}
		else {
			stop = true;
		}
	}
	}
	function func_19(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 18;
		}
		else {
			stop = true;
		}
	}
	}
	function func_20(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_21(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 20;
		}
		else {
			stop = true;
		}
	}
	}
	function func_22(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 17;
		}
		else {
			stop = true;
		}
	}
	}
	function func_23(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 24;
		}
		else {
			stop = true;
		}
	}
	}
	function func_24(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = -1;
		}
		else {
			stop = true;
		}
	}
	}
	function step(int8[] calldata inp) external {

		require(!stop && !bug, "unable to take any further steps");

		if (next_cell == -2) {
			func_start(inp);
			return;
		}
		if (next_cell == -1) {
			func_bug(inp);
			return;
		}
		if (next_cell == 0) {
			func_0(inp);
			return;
		}
		if (next_cell == 1) {
			func_1(inp);
			return;
		}
		if (next_cell == 2) {
			func_2(inp);
			return;
		}
		if (next_cell == 3) {
			func_3(inp);
			return;
		}
		if (next_cell == 4) {
			func_4(inp);
			return;
		}
		if (next_cell == 5) {
			func_5(inp);
			return;
		}
		if (next_cell == 6) {
			func_6(inp);
			return;
		}
		if (next_cell == 7) {
			func_7(inp);
			return;
		}
		if (next_cell == 8) {
			func_8(inp);
			return;
		}
		if (next_cell == 9) {
			func_9(inp);
			return;
		}
		if (next_cell == 10) {
			func_10(inp);
			return;
		}
		if (next_cell == 11) {
			func_11(inp);
			return;
		}
		if (next_cell == 12) {
			func_12(inp);
			return;
		}
		if (next_cell == 13) {
			func_13(inp);
			return;
		}
		if (next_cell == 14) {
			func_14(inp);
			return;
		}
		if (next_cell == 15) {
			func_15(inp);
			return;
		}
		if (next_cell == 16) {
			func_16(inp);
			return;
		}
		if (next_cell == 17) {
			func_17(inp);
			return;
		}
		if (next_cell == 18) {
			func_18(inp);
			return;
		}
		if (next_cell == 19) {
			func_19(inp);
			return;
		}
		if (next_cell == 20) {
			func_20(inp);
			return;
		}
		if (next_cell == 21) {
			func_21(inp);
			return;
		}
		if (next_cell == 22) {
			func_22(inp);
			return;
		}
		if (next_cell == 23) {
			func_23(inp);
			return;
		}
		if (next_cell == 24) {
			func_24(inp);
			return;
		}
	}
	function echidna_noBug() external returns (bool) {return !bug;}
}
