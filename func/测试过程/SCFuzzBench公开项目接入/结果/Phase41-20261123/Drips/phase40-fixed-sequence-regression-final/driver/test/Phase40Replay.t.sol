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
  string memory path="/tmp/phase40-dd1265037da45d6f.tsv";
  vm.writeFile(path,"");
  vm.writeLine(path,string.concat("DEPLOY\t",_address(address(target)),"\t","0x0000000000000000000000000000000000030000"));
  bool allPropertiesPass=true;
  _observe(target,path,0,"initial");
  bool sequenceAlive=true;
  if(sequenceAlive){
   uint256 t0_before=block.timestamp;
   _observe(target,path,1,"before");
   uint256 t0_atCall=block.timestamp;
   vm.prank(address(0x0000000000000000000000000000000000010000));
   uint256 t0_gasBefore=gasleft();
   (bool t0_ok,bytes memory t0_data)=address(target).call{value:0}(abi.encodeWithSignature("give(uint8,uint8,uint128)", uint8(0), uint8(64), uint128(1000000000000000000)));
   uint256 t0_gas= t0_gasBefore-gasleft();
   uint256 t0_after=block.timestamp;
   _observe(target,path,1,"after");
   emit Phase40Transaction(1,address(0x0000000000000000000000000000000000010000),t0_ok,bytes4(keccak256(bytes("give(uint8,uint8,uint128)"))),0,t0_before,t0_after,block.number,t0_gas,t0_data);
   string memory t0_tsv=string.concat("TX\t",_uint(1),"\t","give(uint8,uint8,uint128)");
   t0_tsv=string.concat(t0_tsv,"\t",_address(address(0x0000000000000000000000000000000000010000)),"\t",_uint(0));
   t0_tsv=string.concat(t0_tsv,"\t",t0_ok?"success":"reverted","\t0x",_hex(t0_data));
   t0_tsv=string.concat(t0_tsv,"\t",_uint(t0_gas),"\t",_uint(t0_before),"\t",_uint(t0_atCall));
   t0_tsv=string.concat(t0_tsv,"\t",_uint(t0_after),"\t",_uint(block.number));
   vm.writeLine(path,t0_tsv);
   if(!t0_ok)sequenceAlive=false;
   (bool p0_0ok,bytes memory p0_0data)=address(target).call(abi.encodeWithSignature("invariantAccountingVsTokenBalance()"));
   emit Phase40Property(1,"invariantAccountingVsTokenBalance()",p0_0ok,p0_0data);
   vm.writeLine(path,string.concat("PROP\t",_uint(1),"\t","invariantAccountingVsTokenBalance()","\t",p0_0ok?"passed":"failed","\t0x",_hex(p0_0data)));
   if(!p0_0ok)allPropertiesPass=false;
  }
  if(sequenceAlive){
   uint256 t1_before=block.timestamp;
   _observe(target,path,2,"before");
   uint256 t1_atCall=block.timestamp;
   vm.prank(address(0x0000000000000000000000000000000000010000));
   uint256 t1_gasBefore=gasleft();
   (bool t1_ok,bytes memory t1_data)=address(target).call{value:0}(abi.encodeWithSignature("addStreamImmediatelySqueezable(uint8,uint8,uint160)", uint8(0), uint8(64), uint160(0)));
   uint256 t1_gas= t1_gasBefore-gasleft();
   uint256 t1_after=block.timestamp;
   _observe(target,path,2,"after");
   emit Phase40Transaction(2,address(0x0000000000000000000000000000000000010000),t1_ok,bytes4(keccak256(bytes("addStreamImmediatelySqueezable(uint8,uint8,uint160)"))),0,t1_before,t1_after,block.number,t1_gas,t1_data);
   string memory t1_tsv=string.concat("TX\t",_uint(2),"\t","addStreamImmediatelySqueezable(uint8,uint8,uint160)");
   t1_tsv=string.concat(t1_tsv,"\t",_address(address(0x0000000000000000000000000000000000010000)),"\t",_uint(0));
   t1_tsv=string.concat(t1_tsv,"\t",t1_ok?"success":"reverted","\t0x",_hex(t1_data));
   t1_tsv=string.concat(t1_tsv,"\t",_uint(t1_gas),"\t",_uint(t1_before),"\t",_uint(t1_atCall));
   t1_tsv=string.concat(t1_tsv,"\t",_uint(t1_after),"\t",_uint(block.number));
   vm.writeLine(path,t1_tsv);
   if(!t1_ok)sequenceAlive=false;
   (bool p1_0ok,bytes memory p1_0data)=address(target).call(abi.encodeWithSignature("invariantAccountingVsTokenBalance()"));
   emit Phase40Property(2,"invariantAccountingVsTokenBalance()",p1_0ok,p1_0data);
   vm.writeLine(path,string.concat("PROP\t",_uint(2),"\t","invariantAccountingVsTokenBalance()","\t",p1_0ok?"passed":"failed","\t0x",_hex(p1_0data)));
   if(!p1_0ok)allPropertiesPass=false;
  }
  if(sequenceAlive){
   uint256 t2_before=block.timestamp;
   _observe(target,path,3,"before");
   uint256 t2_atCall=block.timestamp;
   vm.prank(address(0x0000000000000000000000000000000000020000));
   uint256 t2_gasBefore=gasleft();
   (bool t2_ok,bytes memory t2_data)=address(target).call{value:0}(abi.encodeWithSignature("testSqueeze(uint8,uint8)", uint8(64), uint8(0)));
   uint256 t2_gas= t2_gasBefore-gasleft();
   uint256 t2_after=block.timestamp;
   _observe(target,path,3,"after");
   emit Phase40Transaction(3,address(0x0000000000000000000000000000000000020000),t2_ok,bytes4(keccak256(bytes("testSqueeze(uint8,uint8)"))),0,t2_before,t2_after,block.number,t2_gas,t2_data);
   string memory t2_tsv=string.concat("TX\t",_uint(3),"\t","testSqueeze(uint8,uint8)");
   t2_tsv=string.concat(t2_tsv,"\t",_address(address(0x0000000000000000000000000000000000020000)),"\t",_uint(0));
   t2_tsv=string.concat(t2_tsv,"\t",t2_ok?"success":"reverted","\t0x",_hex(t2_data));
   t2_tsv=string.concat(t2_tsv,"\t",_uint(t2_gas),"\t",_uint(t2_before),"\t",_uint(t2_atCall));
   t2_tsv=string.concat(t2_tsv,"\t",_uint(t2_after),"\t",_uint(block.number));
   vm.writeLine(path,t2_tsv);
   if(!t2_ok)sequenceAlive=false;
   (bool p2_0ok,bytes memory p2_0data)=address(target).call(abi.encodeWithSignature("invariantAccountingVsTokenBalance()"));
   emit Phase40Property(3,"invariantAccountingVsTokenBalance()",p2_0ok,p2_0data);
   vm.writeLine(path,string.concat("PROP\t",_uint(3),"\t","invariantAccountingVsTokenBalance()","\t",p2_0ok?"passed":"failed","\t0x",_hex(p2_0data)));
   if(!p2_0ok)allPropertiesPass=false;
  }
  require(allPropertiesPass,"Phase40 property failure");
 }
}
