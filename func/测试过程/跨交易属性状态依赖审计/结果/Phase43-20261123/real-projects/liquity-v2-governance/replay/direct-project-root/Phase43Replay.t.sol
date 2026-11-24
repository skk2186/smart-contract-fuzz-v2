// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import {CryticTester} from "./recon/CryticTester.sol";
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
 function _observe(CryticTester target,string memory path,uint256 index,string memory phase) internal {
 }
 function testPhase40Scenario() public {
  vm.prank(address(0x0000000000000000000000000000000000030000));
  CryticTester target=new CryticTester();
  string memory path="/tmp/phase43-liquity-agent.tsv";
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
   (bool t0_ok,bytes memory t0_data)=address(target).call{value:0}(abi.encodeWithSignature("helper_deployInitiative()"));
   uint256 t0_gas= t0_gasBefore-gasleft();
   uint256 t0_after=block.timestamp;
   _observe(target,path,1,"after");
   emit Phase40Transaction(1,address(0x0000000000000000000000000000000000010000),t0_ok,bytes4(keccak256(bytes("helper_deployInitiative()"))),0,t0_before,t0_after,block.number,t0_gas,t0_data);
   string memory t0_tsv=string.concat("TX\t",_uint(1),"\t","helper_deployInitiative()");
   t0_tsv=string.concat(t0_tsv,"\t",_address(address(0x0000000000000000000000000000000000010000)),"\t",_uint(0));
   t0_tsv=string.concat(t0_tsv,"\t",t0_ok?"success":"reverted","\t0x",_hex(t0_data));
   t0_tsv=string.concat(t0_tsv,"\t",_uint(t0_gas),"\t",_uint(t0_before),"\t",_uint(t0_atCall));
   t0_tsv=string.concat(t0_tsv,"\t",_uint(t0_after),"\t",_uint(block.number));
   vm.writeLine(path,t0_tsv);
   if(!t0_ok)sequenceAlive=false;
   (bool p0_0ok,bytes memory p0_0data)=address(target).call(abi.encodeWithSignature("invariant_GV01()"));
   emit Phase40Property(1,"invariant_GV01()",p0_0ok,p0_0data);
   vm.writeLine(path,string.concat("PROP\t",_uint(1),"\t","invariant_GV01()","\t",p0_0ok?"passed":"failed","\t0x",_hex(p0_0data)));
   if(!p0_0ok)allPropertiesPass=false;
  }
  require(allPropertiesPass,"Phase40 property failure");
 }
}
