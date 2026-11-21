import json,os,subprocess,time,signal,hashlib,traceback
from pathlib import Path
from web3 import Web3
from web3.providers.rpc import HTTPProvider
ROOT=Path("/home/skk/smart-contract-fuzz-v2")
PROJECT=ROOT/"sol/真实项目/DripsSCFuzzBench"
OUT=ROOT/"func/测试过程/SCFuzzBench公开项目接入/结果/Phase39-20261121/Drips/anvil-deployment-and-property-replay.json"
ART=PROJECT/"out/Echidna.sol/Echidna.json"
PORT=18547
args=[str(ROOT/".tools/foundry/bin/anvil"),"--host","127.0.0.1","--port",str(PORT),"--chain-id","31337","--accounts","10","--balance","10000","--gas-limit","100000000","--disable-code-size-limit","--silent"]
proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
result={"argv":args,"artifact":str(ART.relative_to(ROOT)),"artifact_sha256":hashlib.sha256(ART.read_bytes()).hexdigest(),"anvil_accounts":{},"deployment":{},"property_replay":{},"getter_reads":{}}
try:
    w3=Web3(HTTPProvider(f"http://127.0.0.1:{PORT}",request_kwargs={"timeout":5}))
    for _ in range(100):
        if w3.is_connected(): break
        time.sleep(.2)
    if not w3.is_connected(): raise RuntimeError("Anvil RPC did not become ready")
    accounts=w3.eth.accounts
    result["anvil_accounts"]={"chain_id":w3.eth.chain_id,"count":len(accounts),"addresses":accounts,"balances_wei":[str(w3.eth.get_balance(a)) for a in accounts],"timestamp":w3.eth.get_block("latest")["timestamp"]}
    artifact=json.loads(ART.read_text())
    abi=artifact["abi"]
    bytecode=artifact["bytecode"]["object"] if isinstance(artifact["bytecode"],dict) else artifact["bytecode"]
    if bytecode.startswith("0x"): bytecode=bytecode[2:]
    factory=w3.eth.contract(abi=abi,bytecode="0x"+bytecode)
    txhash=factory.constructor().transact({"from":accounts[0],"gas":95000000})
    receipt=w3.eth.wait_for_transaction_receipt(txhash,timeout=60)
    result["deployment"]={"tx_hash":txhash.hex(),"status":receipt.status,"gas_used":receipt.gasUsed,"contract_address":receipt.contractAddress,"block_number":receipt.blockNumber}
    signatures=[x["name"]+"("+",".join(i["type"] for i in x.get("inputs",[]))+")" for x in abi if x.get("type")=="function"]
    result["abi_functions"]=signatures
    if receipt.status==1:
        c=w3.eth.contract(address=receipt.contractAddress,abi=abi)
        actor_addresses=[]
        for i in range(4):
            try: actor_addresses.append(c.functions.getAccount(i).call())
            except Exception as e: actor_addresses.append("read_failed:"+str(e))
        result["anvil_accounts"]["harness_actor_addresses"]=actor_addresses
        result["anvil_accounts"]["harness_actors_are_unlocked_anvil_accounts"]=[x.lower() in {a.lower() for a in accounts} if x.startswith("0x") else False for x in actor_addresses]
        pair=[actor_addresses[1],actor_addresses[0]] if len(actor_addresses)>1 and all(x.startswith("0x") for x in actor_addresses[:2]) else None
        if pair:
            try: result["getter_reads"]["squeezable_before"]=str(c.functions.getSqueezableAmount(pair[0],pair[1]).call())
            except Exception as e: result["getter_reads"]["squeezable_before_error"]=str(e)
        fn=next((f for f in c.functions if f.fn_name=="testSqueezableAmountCantBeUndone"),None)
        if fn is not None:
            try:
                testfn=c.get_function_by_name("testSqueezableAmountCantBeUndone")(0,1,1000,0,100,0)
                txh=testfn.transact({"from":accounts[0],"gas":20000000})
                rr=w3.eth.wait_for_transaction_receipt(txh,timeout=60)
                result["property_replay"]={"function":"testSqueezableAmountCantBeUndone(uint8,uint8,uint160,uint32,uint32,int128)","args":[0,1,1000,0,100,0],"tx_hash":txh.hex(),"status":rr.status,"gas_used":rr.gasUsed,"block_number":rr.blockNumber}
                try:
                    trace=w3.provider.make_request("debug_traceTransaction",[txh.hex(),{}])
                    result["property_replay"]["trace_result"]={"error":trace.get("error"),"struct_logs":len(trace.get("result",{}).get("structLogs",[]))}
                except Exception as e: result["property_replay"]["trace_error"]=str(e)
            except Exception as e: result["property_replay"]={"function":"testSqueezableAmountCantBeUndone","error":str(e)}
        if pair:
            try: result["getter_reads"]["squeezable_after"]=str(c.functions.getSqueezableAmount(pair[0],pair[1]).call())
            except Exception as e: result["getter_reads"]["squeezable_after_error"]=str(e)
    result["status"]="completed_probe"
except Exception as e:
    result["status"]="probe_error"
    result["error"]=str(e)
    result["traceback"]=traceback.format_exc()
finally:
    try: proc.terminate(); proc.wait(timeout=5)
    except Exception:
        try: os.killpg(proc.pid,signal.SIGKILL)
        except Exception: pass
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:result.get(k) for k in ["status","anvil_accounts","deployment","property_replay","getter_reads"]},ensure_ascii=False,indent=2))
