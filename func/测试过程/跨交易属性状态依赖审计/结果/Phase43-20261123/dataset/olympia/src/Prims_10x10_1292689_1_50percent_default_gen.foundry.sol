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
		if (inp[0] < 0) {
			next_cell = -2;
		}
		else if (inp[0] >= 0) {
			next_cell = 10;
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
			next_cell = 11;
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
		if (inp[0] < 0) {
			next_cell = 1;
		}
		else if (inp[0] >= 0) {
			next_cell = 3;
		}
		else {
			stop = true;
		}
	}
	}
	function func_3(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 2;
		}
		else if (inp[0] < 42) {
			next_cell = 13;
		}
		else if (inp[0] >= 42) {
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
		if (inp[0] < 0) {
			next_cell = 14;
		}
		else if (inp[0] >= 0) {
			next_cell = 5;
		}
		else {
			stop = true;
		}
	}
	}
	function func_5(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 15;
		}
		else {
			stop = true;
		}
	}
	}
	function func_6(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 16;
		}
		else if (inp[0] >= 0) {
			next_cell = 7;
		}
		else {
			stop = true;
		}
	}
	}
	function func_7(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 6;
		}
		else if (inp[0] >= 0) {
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
			next_cell = 18;
		}
		else if (inp[0] >= 0) {
			next_cell = 9;
		}
		else {
			stop = true;
		}
	}
	}
	function func_9(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_10(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 20;
		}
		else if (inp[0] >= 0) {
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
		if (inp[0] < -43) {
			next_cell = 1;
		}
		else if (inp[0] < 42) {
			next_cell = 10;
		}
		else if (inp[0] >= 42) {
			next_cell = 21;
		}
		else {
			stop = true;
		}
	}
	}
	function func_12(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

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

	}
	}
	function func_15(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 25;
		}
		else if (inp[0] >= 0) {
			next_cell = 16;
		}
		else {
			stop = true;
		}
	}
	}
	function func_16(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 6;
		}
		else if (inp[0] < 42) {
			next_cell = 15;
		}
		else if (inp[0] >= 42) {
			next_cell = 26;
		}
		else {
			stop = true;
		}
	}
	}
	function func_17(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 27;
		}
		else {
			stop = true;
		}
	}
	}
	function func_18(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 8;
		}
		else if (inp[0] < 42) {
			next_cell = 17;
		}
		else if (inp[0] >= 42) {
			next_cell = 28;
		}
		else {
			stop = true;
		}
	}
	}
	function func_19(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_20(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 10;
		}
		else if (inp[0] >= 0) {
			next_cell = 30;
		}
		else {
			stop = true;
		}
	}
	}
	function func_21(int8[] memory inp) internal {
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
	function func_22(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 12;
		}
		else if (inp[0] >= 0) {
			next_cell = 23;
		}
		else {
			stop = true;
		}
	}
	}
	function func_23(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 22;
		}
		else if (inp[0] >= 0) {
			next_cell = 33;
		}
		else {
			stop = true;
		}
	}
	}
	function func_24(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 23;
		}
		else if (inp[0] < 42) {
			next_cell = 34;
		}
		else if (inp[0] >= 42) {
			next_cell = 25;
		}
		else {
			stop = true;
		}
	}
	}
	function func_25(int8[] memory inp) internal {
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
	function func_26(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_27(int8[] memory inp) internal {
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
	function func_28(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 38;
		}
		else if (inp[0] >= 0) {
			next_cell = 29;
		}
		else {
			stop = true;
		}
	}
	}
	function func_29(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 19;
		}
		else if (inp[0] >= 0) {
			next_cell = 28;
		}
		else {
			stop = true;
		}
	}
	}
	function func_30(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 20;
		}
		else if (inp[0] >= 0) {
			next_cell = 40;
		}
		else {
			stop = true;
		}
	}
	}
	function func_31(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_32(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 31;
		}
		else {
			stop = true;
		}
	}
	}
	function func_33(int8[] memory inp) internal {
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
	function func_34(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 44;
		}
		else {
			stop = true;
		}
	}
	}
	function func_35(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_36(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 35;
		}
		else if (inp[0] < 42) {
			next_cell = 46;
		}
		else if (inp[0] >= 42) {
			next_cell = 37;
		}
		else {
			stop = true;
		}
	}
	}
	function func_37(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 36;
		}
		else {
			stop = true;
		}
	}
	}
	function func_38(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 37;
		}
		else if (inp[0] >= 0) {
			next_cell = 39;
		}
		else {
			stop = true;
		}
	}
	}
	function func_39(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_40(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 30;
		}
		else {
			stop = true;
		}
	}
	}
	function func_41(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 42;
		}
		else {
			stop = true;
		}
	}
	}
	function func_42(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 32;
		}
		else if (inp[0] < 42) {
			next_cell = 41;
		}
		else if (inp[0] >= 42) {
			next_cell = 52;
		}
		else {
			stop = true;
		}
	}
	}
	function func_43(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 53;
		}
		else {
			stop = true;
		}
	}
	}
	function func_44(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 43;
		}
		else if (inp[0] >= 0) {
			next_cell = 54;
		}
		else {
			stop = true;
		}
	}
	}
	function func_45(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_46(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 36;
		}
		else if (inp[0] >= 0) {
			next_cell = 47;
		}
		else {
			stop = true;
		}
	}
	}
	function func_47(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 57;
		}
		else if (inp[0] >= 0) {
			next_cell = 48;
		}
		else {
			stop = true;
		}
	}
	}
	function func_48(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 47;
		}
		else if (inp[0] >= 0) {
			next_cell = 49;
		}
		else {
			stop = true;
		}
	}
	}
	function func_49(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 59;
		}
		else {
			stop = true;
		}
	}
	}
	function func_50(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_51(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 50;
		}
		else if (inp[0] >= 0) {
			next_cell = 52;
		}
		else {
			stop = true;
		}
	}
	}
	function func_52(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 42;
		}
		else if (inp[0] < 42) {
			next_cell = 51;
		}
		else if (inp[0] >= 42) {
			next_cell = 53;
		}
		else {
			stop = true;
		}
	}
	}
	function func_53(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 43;
		}
		else if (inp[0] >= 0) {
			next_cell = 52;
		}
		else {
			stop = true;
		}
	}
	}
	function func_54(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_55(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 45;
		}
		else if (inp[0] < 42) {
			next_cell = 65;
		}
		else if (inp[0] >= 42) {
			next_cell = 56;
		}
		else {
			stop = true;
		}
	}
	}
	function func_56(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 55;
		}
		else if (inp[0] >= 0) {
			next_cell = 57;
		}
		else {
			stop = true;
		}
	}
	}
	function func_57(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -64) {
			next_cell = 47;
		}
		else if (inp[0] < 0) {
			next_cell = 56;
		}
		else if (inp[0] < 64) {
			next_cell = 67;
		}
		else if (inp[0] >= 64) {
			next_cell = 58;
		}
		else {
			stop = true;
		}
	}
	}
	function func_58(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 57;
		}
		else {
			stop = true;
		}
	}
	}
	function func_59(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 49;
		}
		else {
			stop = true;
		}
	}
	}
	function func_60(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_61(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 62;
		}
		else {
			stop = true;
		}
	}
	}
	function func_62(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 61;
		}
		else if (inp[0] < 42) {
			next_cell = 72;
		}
		else if (inp[0] >= 42) {
			next_cell = 63;
		}
		else {
			stop = true;
		}
	}
	}
	function func_63(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 62;
		}
		else {
			stop = true;
		}
	}
	}
	function func_64(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 63;
		}
		else {
			stop = true;
		}
	}
	}
	function func_65(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 64;
		}
		else if (inp[0] < 42) {
			next_cell = 75;
		}
		else if (inp[0] >= 42) {
			next_cell = 66;
		}
		else {
			stop = true;
		}
	}
	}
	function func_66(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 65;
		}
		else {
			stop = true;
		}
	}
	}
	function func_67(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 57;
		}
		else if (inp[0] >= 0) {
			next_cell = 68;
		}
		else {
			stop = true;
		}
	}
	}
	function func_68(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 67;
		}
		else if (inp[0] >= 0) {
			next_cell = 69;
		}
		else {
			stop = true;
		}
	}
	}
	function func_69(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 79;
		}
		else {
			stop = true;
		}
	}
	}
	function func_70(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 60;
		}
		else if (inp[0] >= 0) {
			next_cell = 80;
		}
		else {
			stop = true;
		}
	}
	}
	function func_71(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 70;
		}
		else if (inp[0] >= 0) {
			next_cell = 72;
		}
		else {
			stop = true;
		}
	}
	}
	function func_72(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 62;
		}
		else if (inp[0] < 42) {
			next_cell = 71;
		}
		else if (inp[0] >= 42) {
			next_cell = 82;
		}
		else {
			stop = true;
		}
	}
	}
	function func_73(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 83;
		}
		else if (inp[0] >= 0) {
			next_cell = 74;
		}
		else {
			stop = true;
		}
	}
	}
	function func_74(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 73;
		}
		else if (inp[0] >= 0) {
			next_cell = 75;
		}
		else {
			stop = true;
		}
	}
	}
	function func_75(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -64) {
			next_cell = 65;
		}
		else if (inp[0] < 0) {
			next_cell = 74;
		}
		else if (inp[0] < 64) {
			next_cell = 85;
		}
		else if (inp[0] >= 64) {
			next_cell = 76;
		}
		else {
			stop = true;
		}
	}
	}
	function func_76(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 75;
		}
		else {
			stop = true;
		}
	}
	}
	function func_77(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 87;
		}
		else if (inp[0] >= 0) {
			next_cell = 78;
		}
		else {
			stop = true;
		}
	}
	}
	function func_78(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_79(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 89;
		}
		else {
			stop = true;
		}
	}
	}
	function func_80(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 70;
		}
		else if (inp[0] >= 0) {
			next_cell = 90;
		}
		else {
			stop = true;
		}
	}
	}
	function func_81(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_82(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 81;
		}
		else if (inp[0] >= 0) {
			next_cell = 92;
		}
		else {
			stop = true;
		}
	}
	}
	function func_83(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_84(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 94;
		}
		else {
			stop = true;
		}
	}
	}
	function func_85(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -64) {
			next_cell = 75;
		}
		else if (inp[0] < 0) {
			next_cell = 84;
		}
		else if (inp[0] < 64) {
			next_cell = 95;
		}
		else if (inp[0] >= 64) {
			next_cell = 86;
		}
		else {
			stop = true;
		}
	}
	}
	function func_86(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 85;
		}
		else if (inp[0] < 42) {
			next_cell = 96;
		}
		else if (inp[0] >= 42) {
			next_cell = 87;
		}
		else {
			stop = true;
		}
	}
	}
	function func_87(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < -43) {
			next_cell = 77;
		}
		else if (inp[0] < 42) {
			next_cell = 97;
		}
		else if (inp[0] >= 42) {
			next_cell = 88;
		}
		else {
			stop = true;
		}
	}
	}
	function func_88(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 98;
		}
		else {
			stop = true;
		}
	}
	}
	function func_89(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_90(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 91;
		}
		else {
			stop = true;
		}
	}
	}
	function func_91(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_92(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_93(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 94;
		}
		else {
			stop = true;
		}
	}
	}
	function func_94(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 84;
		}
		else if (inp[0] >= 0) {
			next_cell = 93;
		}
		else {
			stop = true;
		}
	}
	}
	function func_95(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 85;
		}
		else {
			stop = true;
		}
	}
	}
	function func_96(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 86;
		}
		else {
			stop = true;
		}
	}
	}
	function func_97(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);

	}
	}
	function func_98(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (true) {
			next_cell = 99;
		}
		else {
			stop = true;
		}
	}
	}
	function func_99(int8[] memory inp) internal {
	unchecked{
		require(inp.length >= 1);
		if (inp[0] < 0) {
			next_cell = 98;
		}
		else if (inp[0] >= 0) {
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
		if (next_cell == 25) {
			func_25(inp);
			return;
		}
		if (next_cell == 26) {
			func_26(inp);
			return;
		}
		if (next_cell == 27) {
			func_27(inp);
			return;
		}
		if (next_cell == 28) {
			func_28(inp);
			return;
		}
		if (next_cell == 29) {
			func_29(inp);
			return;
		}
		if (next_cell == 30) {
			func_30(inp);
			return;
		}
		if (next_cell == 31) {
			func_31(inp);
			return;
		}
		if (next_cell == 32) {
			func_32(inp);
			return;
		}
		if (next_cell == 33) {
			func_33(inp);
			return;
		}
		if (next_cell == 34) {
			func_34(inp);
			return;
		}
		if (next_cell == 35) {
			func_35(inp);
			return;
		}
		if (next_cell == 36) {
			func_36(inp);
			return;
		}
		if (next_cell == 37) {
			func_37(inp);
			return;
		}
		if (next_cell == 38) {
			func_38(inp);
			return;
		}
		if (next_cell == 39) {
			func_39(inp);
			return;
		}
		if (next_cell == 40) {
			func_40(inp);
			return;
		}
		if (next_cell == 41) {
			func_41(inp);
			return;
		}
		if (next_cell == 42) {
			func_42(inp);
			return;
		}
		if (next_cell == 43) {
			func_43(inp);
			return;
		}
		if (next_cell == 44) {
			func_44(inp);
			return;
		}
		if (next_cell == 45) {
			func_45(inp);
			return;
		}
		if (next_cell == 46) {
			func_46(inp);
			return;
		}
		if (next_cell == 47) {
			func_47(inp);
			return;
		}
		if (next_cell == 48) {
			func_48(inp);
			return;
		}
		if (next_cell == 49) {
			func_49(inp);
			return;
		}
		if (next_cell == 50) {
			func_50(inp);
			return;
		}
		if (next_cell == 51) {
			func_51(inp);
			return;
		}
		if (next_cell == 52) {
			func_52(inp);
			return;
		}
		if (next_cell == 53) {
			func_53(inp);
			return;
		}
		if (next_cell == 54) {
			func_54(inp);
			return;
		}
		if (next_cell == 55) {
			func_55(inp);
			return;
		}
		if (next_cell == 56) {
			func_56(inp);
			return;
		}
		if (next_cell == 57) {
			func_57(inp);
			return;
		}
		if (next_cell == 58) {
			func_58(inp);
			return;
		}
		if (next_cell == 59) {
			func_59(inp);
			return;
		}
		if (next_cell == 60) {
			func_60(inp);
			return;
		}
		if (next_cell == 61) {
			func_61(inp);
			return;
		}
		if (next_cell == 62) {
			func_62(inp);
			return;
		}
		if (next_cell == 63) {
			func_63(inp);
			return;
		}
		if (next_cell == 64) {
			func_64(inp);
			return;
		}
		if (next_cell == 65) {
			func_65(inp);
			return;
		}
		if (next_cell == 66) {
			func_66(inp);
			return;
		}
		if (next_cell == 67) {
			func_67(inp);
			return;
		}
		if (next_cell == 68) {
			func_68(inp);
			return;
		}
		if (next_cell == 69) {
			func_69(inp);
			return;
		}
		if (next_cell == 70) {
			func_70(inp);
			return;
		}
		if (next_cell == 71) {
			func_71(inp);
			return;
		}
		if (next_cell == 72) {
			func_72(inp);
			return;
		}
		if (next_cell == 73) {
			func_73(inp);
			return;
		}
		if (next_cell == 74) {
			func_74(inp);
			return;
		}
		if (next_cell == 75) {
			func_75(inp);
			return;
		}
		if (next_cell == 76) {
			func_76(inp);
			return;
		}
		if (next_cell == 77) {
			func_77(inp);
			return;
		}
		if (next_cell == 78) {
			func_78(inp);
			return;
		}
		if (next_cell == 79) {
			func_79(inp);
			return;
		}
		if (next_cell == 80) {
			func_80(inp);
			return;
		}
		if (next_cell == 81) {
			func_81(inp);
			return;
		}
		if (next_cell == 82) {
			func_82(inp);
			return;
		}
		if (next_cell == 83) {
			func_83(inp);
			return;
		}
		if (next_cell == 84) {
			func_84(inp);
			return;
		}
		if (next_cell == 85) {
			func_85(inp);
			return;
		}
		if (next_cell == 86) {
			func_86(inp);
			return;
		}
		if (next_cell == 87) {
			func_87(inp);
			return;
		}
		if (next_cell == 88) {
			func_88(inp);
			return;
		}
		if (next_cell == 89) {
			func_89(inp);
			return;
		}
		if (next_cell == 90) {
			func_90(inp);
			return;
		}
		if (next_cell == 91) {
			func_91(inp);
			return;
		}
		if (next_cell == 92) {
			func_92(inp);
			return;
		}
		if (next_cell == 93) {
			func_93(inp);
			return;
		}
		if (next_cell == 94) {
			func_94(inp);
			return;
		}
		if (next_cell == 95) {
			func_95(inp);
			return;
		}
		if (next_cell == 96) {
			func_96(inp);
			return;
		}
		if (next_cell == 97) {
			func_97(inp);
			return;
		}
		if (next_cell == 98) {
			func_98(inp);
			return;
		}
		if (next_cell == 99) {
			func_99(inp);
			return;
		}
	}
}
import "forge-std/Test.sol";
contract TestMaze is Test {
    Maze m;
    function setUp() external {
        m = new Maze();
    }
    function invariant_no_bug() external {
        if (m.bug()) { fail(); }
    }
}