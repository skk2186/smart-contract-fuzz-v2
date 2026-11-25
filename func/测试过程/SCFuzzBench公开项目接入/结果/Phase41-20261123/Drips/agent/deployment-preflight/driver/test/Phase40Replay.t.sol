// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import {Echidna} from "phase40-source/echidna/Echidna.sol";
interface VmPhase40 {
 function prank(address sender) external;
 function prank(address sender, address origin) external;
 function warp(uint256 timestamp) external;
 function roll(uint256 number) external;
 function load(address target, bytes32 slot) external view returns (bytes32);
 function writeFile(string calldata path, string calldata data) external;
 function writeLine(string calldata path, string calldata data) external;
}
contract Phase40ReplayTest {
 VmPhase40 private constant vm = VmPhase40(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);
 event Phase40Transaction(uint256 indexed index,address indexed sender,bool success,bytes4 selector,uint256 value,uint256 timestampBefore,uint256 timestampAfter,uint256 blockNumber,uint256 gasEstimate,bytes returnData);
 event Phase40Property(uint256 indexed index,string signature,bool success,bytes returnData);
 function _hex(bytes memory data) internal pure returns (string memory) {
  bytes16 a = "0123456789abcdef"; bytes memory o = new bytes(data.length * 2);
  for (uint256 i; i < data.length; i++) { o[i*2]=a[uint8(data[i])>>4]; o[i*2+1]=a[uint8(data[i])&15]; } return string(o); }
 function _uint(uint256 n) internal pure returns (string memory) { if(n==0)return "0"; uint256 s; uint256 c=n; while(c!=0){s++;c/=10;} bytes memory b=new bytes(s); while(n!=0){s--;b[s]=bytes1(uint8(48+n%10));n/=10;} return string(b); }
 function _address(address a) internal pure returns (string memory) { return string.concat("0x",_hex(abi.encodePacked(a))); }
 function _writeObservation(string memory path,uint256 index,string memory phase,string memory name,address receiver,bytes memory input) internal {
  (bool ok,bytes memory data)=receiver.staticcall(input);
  vm.writeLine(path,string.concat("OBS\t",_uint(index),"\t",phase,"\t",name,"\t",ok?"success":"error","\t0x",_hex(data),"\t",_address(receiver)));
 }
 function _observe(Echidna target,string memory path,uint256 index,string memory phase) internal {
  _writeObservation(path,index,phase,"user0_token_balance",address(uint160(uint256(vm.load(address(target),bytes32(uint256(4)))))),abi.encodeWithSignature("balanceOf(address)", address(0x0000000000000000000000000000000000010000)));
  _writeObservation(path,index,phase,"user1_token_balance",address(uint160(uint256(vm.load(address(target),bytes32(uint256(4)))))),abi.encodeWithSignature("balanceOf(address)", address(0x0000000000000000000000000000000000020000)));
  _writeObservation(path,index,phase,"drips_token_balance",address(uint160(uint256(vm.load(address(target),bytes32(uint256(4)))))),abi.encodeWithSignature("balanceOf(address)", address(uint160(uint256(vm.load(address(target), bytes32(uint256(5))))))));
  _writeObservation(path,index,phase,"receiver_splittable",address(uint160(uint256(vm.load(address(target),bytes32(uint256(5)))))),abi.encodeWithSignature("splittable(uint256,address)", uint256(131072), address(uint160(uint256(vm.load(address(target), bytes32(uint256(4))))))));
 }
 function testPhase40Scenario() public {
  vm.prank(address(0x0000000000000000000000000000000000030000));
  Echidna target=new Echidna();
  string memory path="/tmp/phase40-e98dfb37e6427343.tsv";
  vm.writeFile(path,"");
  vm.writeLine(path,string.concat("DEPLOY\t",_address(address(target)),"\t","0x0000000000000000000000000000000000030000"));
  bool allPropertiesPass=true;
  _observe(target,path,0,"initial");
  bool sequenceAlive=true;
  require(allPropertiesPass,"Phase40 property failure");
 }
}
