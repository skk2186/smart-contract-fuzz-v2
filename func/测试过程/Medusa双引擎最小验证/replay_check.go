package main

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"math/big"
	"os"
	"strings"

	"github.com/crytic/medusa-geth/accounts/abi"
	"github.com/crytic/medusa-geth/common"
	core "github.com/crytic/medusa-geth/core"
	coretypes "github.com/crytic/medusa-geth/core/types"
	"github.com/crytic/medusa-geth/crypto"
	"github.com/crytic/medusa/chain"
	"github.com/crytic/medusa/fuzzing"
	"github.com/crytic/medusa/fuzzing/calls"
	"github.com/crytic/medusa/fuzzing/config"
	"github.com/crytic/medusa/fuzzing/contracts"
	"github.com/crytic/medusa/fuzzing/executiontracer"
	"github.com/crytic/medusa/utils"
)

type options struct {
	caseName string
	config   string
	corpus   string
	target   string
	index    int
	output   string
}

type eventRecord struct {
	Address string   `json:"address"`
	Topics  []string `json:"topics"`
	Data    string   `json:"data"`
}

type frameRecord struct {
	From        string        `json:"from"`
	To          string        `json:"to"`
	Contract    string        `json:"contract,omitempty"`
	Input       string        `json:"input"`
	ReturnData  string        `json:"return_data,omitempty"`
	ReturnError string        `json:"return_error,omitempty"`
	Events      []eventRecord `json:"events,omitempty"`
	Children    []frameRecord `json:"children,omitempty"`
}

type transactionRecord struct {
	Position       int           `json:"position"`
	Function       string        `json:"function"`
	From           string        `json:"from"`
	To             string        `json:"to"`
	Nonce          uint64        `json:"nonce"`
	Value          string        `json:"value"`
	BlockNumber    uint64        `json:"executed_block_number"`
	BlockTimestamp uint64        `json:"executed_block_timestamp"`
	GasUsed        uint64        `json:"gas_used"`
	EVMFailed      bool          `json:"evm_failed"`
	OuterRollback  bool          `json:"outer_rollback"`
	ExecutionError string        `json:"execution_error,omitempty"`
	ReceiptStatus  uint64        `json:"receipt_status"`
	InternalErrors []string      `json:"internal_call_errors"`
	Trace          *frameRecord  `json:"execution_trace,omitempty"`
	ReceiptEvents  []eventRecord `json:"receipt_events,omitempty"`
}

func die(err error) {
	_ = json.NewEncoder(os.Stderr).Encode(map[string]any{"status": "error", "error": err.Error()})
	os.Exit(2)
}

func hexData(data []byte) string { return "0x" + hex.EncodeToString(data) }

func traceFrame(frame *executiontracer.CallFrame) frameRecord {
	result := frameRecord{
		From: frame.SenderAddress.Hex(), To: frame.ToAddress.Hex(), Contract: frame.ToContractName,
		Input: hexData(frame.InputData), ReturnData: hexData(frame.ReturnData),
		Events: make([]eventRecord, 0), Children: make([]frameRecord, 0),
	}
	if frame.ReturnError != nil {
		result.ReturnError = frame.ReturnError.Error()
	}
	for _, operation := range frame.Operations {
		switch value := operation.(type) {
		case *executiontracer.CallFrame:
			result.Children = append(result.Children, traceFrame(value))
		case *coretypes.Log:
			event := eventRecord{Address: value.Address.Hex(), Data: hexData(value.Data)}
			for _, topic := range value.Topics {
				event.Topics = append(event.Topics, topic.Hex())
			}
			result.Events = append(result.Events, event)
		}
	}
	return result
}

func receiptEvents(receipt *coretypes.Receipt) []eventRecord {
	if receipt == nil {
		return nil
	}
	result := make([]eventRecord, 0, len(receipt.Logs))
	for _, log := range receipt.Logs {
		event := eventRecord{Address: log.Address.Hex(), Data: hexData(log.Data)}
		for _, topic := range log.Topics {
			event.Topics = append(event.Topics, topic.Hex())
		}
		result = append(result, event)
	}
	return result
}

func runGetterAt(testChain *chain.TestChain, target common.Address, contractABI abi.ABI, from common.Address, name string, args ...any) ([]any, error) {
	packed, err := contractABI.Pack(name, args...)
	if err != nil {
		return nil, err
	}
	message := &calls.CallMessage{
		From: from, To: &target, Nonce: testChain.State().GetNonce(from), Value: big.NewInt(0), GasLimit: 12_500_000,
		GasPrice: big.NewInt(0), GasFeeCap: big.NewInt(0), GasTipCap: big.NewInt(0), Data: packed,
	}
	result, err := testChain.CallContract(message.ToCoreMessage(), nil)
	if err != nil {
		return nil, err
	}
	if result.Failed() {
		return nil, result.Err
	}
	return contractABI.Unpack(name, result.Return())
}

func oneEvent(receipt *coretypes.Receipt, event abi.Event) bool {
	if receipt == nil {
		return false
	}
	for _, log := range receipt.Logs {
		if len(log.Topics) > 0 && log.Topics[0] == event.ID {
			return true
		}
	}
	return false
}

func main() {
	var opts options
	flag.StringVar(&opts.caseName, "case", "", "BeeStorage or Immutable")
	flag.StringVar(&opts.config, "config", "", "Medusa configuration JSON")
	flag.StringVar(&opts.corpus, "corpus", "", "converted call-sequence JSON")
	flag.StringVar(&opts.target, "target", "", "mapped target address")
	flag.IntVar(&opts.index, "target-index", -1, "zero-based target transaction index")
	flag.StringVar(&opts.output, "out", "", "machine-readable result JSON")
	flag.Parse()
	if opts.caseName != "BeeStorage" && opts.caseName != "Immutable" {
		die(errors.New("--case 仅支持 BeeStorage 或 Immutable"))
	}
	if opts.config == "" || opts.corpus == "" || opts.target == "" || opts.output == "" || opts.index < 0 {
		die(errors.New("--config、--corpus、--target、--target-index、--out 均为必需参数"))
	}
	targetAddress := common.HexToAddress(opts.target)
	projectConfig, err := config.ReadProjectConfigFromFile(opts.config, "crytic-compile")
	if err != nil {
		die(fmt.Errorf("读取 Medusa 配置失败: %w", err))
	}
	fuzzer, err := fuzzing.NewFuzzer(*projectConfig)
	if err != nil {
		die(fmt.Errorf("Medusa 初始化/编译失败: %w", err))
	}
	testChain, deployed, err := fuzzer.CreateTestChainForCleaning()
	if err != nil {
		die(fmt.Errorf("Medusa 部署失败: %w", err))
	}
	defer testChain.Close()

	corpusBytes, err := os.ReadFile(opts.corpus)
	if err != nil {
		die(err)
	}
	var sequence calls.CallSequence
	if err := json.Unmarshal(corpusBytes, &sequence); err != nil {
		die(fmt.Errorf("Medusa 原生 corpus 解析失败: %w", err))
	}
	if len(sequence) == 0 || opts.index >= len(sequence) {
		die(fmt.Errorf("corpus 序列长度 %d 与 target-index %d 不符", len(sequence), opts.index))
	}
	targetContract, ok := deployed[targetAddress]
	if !ok {
		die(fmt.Errorf("目标 Harness 未在 Medusa 配置地址部署：%s", targetAddress.Hex()))
	}
	propertyName := "echidna_stamp_internal_pot_not_above_contract_balance()"
	if opts.caseName == "Immutable" {
		propertyName = "echidna_complex_transfer_sequence()"
	}
	propertyDetected := false
	for _, method := range targetContract.PropertyTestMethods {
		if method.Sig == propertyName {
			propertyDetected = true
		}
	}
	tracer := executiontracer.NewExecutionTracer(fuzzer.ContractDefinitions(), testChain, config.VeryVeryVerbose)
	defer tracer.Close()
	transactions := make([]transactionRecord, 0, len(sequence))
	var targetState map[string]any
	var internalErrors []string
	fetch := func(index int) (*calls.CallSequenceElement, error) {
		if index >= len(sequence) {
			return nil, nil
		}
		element := sequence[index]
		if element.Call == nil || element.Call.To == nil {
			return nil, fmt.Errorf("交易 %d 缺少 call.to", index+1)
		}
		contract, found := deployed[*element.Call.To]
		if !found {
			return nil, fmt.Errorf("交易 %d 目标未部署：%s", index+1, element.Call.To.Hex())
		}
		element.Contract = contract
		return element, nil
	}
	check := func(executed calls.CallSequence) (bool, error) {
		index := len(executed) - 1
		element := executed[index]
		method, methodErr := element.Contract.CompiledContract().Abi.MethodById(element.Call.Data[:4])
		if methodErr != nil {
			return false, fmt.Errorf("交易 %d calldata selector 无法解码：%w", index+1, methodErr)
		}
		item := transactionRecord{
			Position: index + 1, Function: method.Sig, From: element.Call.From.Hex(), To: element.Call.To.Hex(),
			Nonce: element.Call.Nonce, Value: element.Call.Value.String(), BlockNumber: element.ChainReference.BlockNumber,
			BlockTimestamp: element.ChainReference.BlockTimestamp, InternalErrors: make([]string, 0),
		}
		messageResults := element.ChainReference.MessageResults()
		if messageResults != nil {
			item.ReceiptEvents = receiptEvents(messageResults.Receipt)
			if messageResults.Receipt != nil {
				item.ReceiptStatus = messageResults.Receipt.Status
			}
			if messageResults.ExecutionResult != nil {
				item.GasUsed = messageResults.ExecutionResult.UsedGas
				item.EVMFailed = messageResults.ExecutionResult.Failed()
				if messageResults.ExecutionResult.Err != nil {
					item.ExecutionError = messageResults.ExecutionResult.Err.Error()
				}
			}
			item.OuterRollback = item.EVMFailed || item.ReceiptStatus != coretypes.ReceiptStatusSuccessful
		}
		hash := utils.MessageToTransaction(element.Call.ToCoreMessage()).Hash()
		trace := tracer.GetTrace(hash)
		frameErrors := make([]string, 0)
		if trace != nil && trace.TopLevelCallFrame != nil {
			item.Trace = ptrFrame(traceFrame(trace.TopLevelCallFrame))
			collectFrameErrors(trace.TopLevelCallFrame, &frameErrors)
		}
		item.InternalErrors = frameErrors
		internalErrors = append(internalErrors, frameErrors...)
		transactions = append(transactions, item)

		if index == opts.index {
			targetState = verifyTargetState(opts.caseName, testChain, targetAddress, targetContract.CompiledContract().Abi, deployed, element, fuzzer.SenderAddresses()[0])
		}
		return false, nil
	}
	_, replayErr := calls.ExecuteCallSequenceIteratively(testChain, fetch, check, tracer.NativeTracer())
	if replayErr != nil {
		die(fmt.Errorf("序列回放失败: %w", replayErr))
	}

	propertyResult, propertyErr := runGetterAt(testChain, targetAddress, targetContract.CompiledContract().Abi, fuzzer.SenderAddresses()[0], strings.TrimSuffix(propertyName, "()"))
	var propertyValue any
	if propertyErr != nil {
		propertyValue = map[string]any{"error": propertyErr.Error()}
	} else if len(propertyResult) > 0 {
		propertyValue = propertyResult[0]
	}
	allOuterSucceeded := len(transactions) == len(sequence)
	for _, tx := range transactions {
		allOuterSucceeded = allOuterSucceeded && !tx.OuterRollback
	}
	targetSucceeded := opts.index < len(transactions) && !transactions[opts.index].OuterRollback
	stateEstablished := targetState != nil && targetState["established"] == true
	result := map[string]any{
		"status": "replayed", "engine": "Medusa", "case": opts.caseName,
		"medusa_property_detected": propertyDetected, "target_property": propertyName,
		"corpus_format_valid": true, "sequence_loaded": true,
		"sequence_length": len(sequence), "transactions": transactions,
		"all_transactions_replayed":        len(transactions) == len(sequence),
		"all_outer_transactions_succeeded": allOuterSucceeded,
		"target_transaction_succeeded":     targetSucceeded,
		"target_state":                     targetState, "target_state_established": stateEstablished,
		"target_property_result_after_sequence":                               propertyValue,
		"target_property_call_error":                                          errorText(propertyErr),
		"internal_call_errors":                                                internalErrors,
		"source_initial_timestamp_and_block_not_configurable_in_medusa_1_5_1": true,
	}
	if !propertyDetected || !allOuterSucceeded || !targetSucceeded || !stateEstablished {
		result["status"] = "failed_checks"
	}
	data, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		die(err)
	}
	if err := os.WriteFile(opts.output, append(data, '\n'), 0o644); err != nil {
		die(err)
	}
	_, _ = os.Stdout.Write(append(data, '\n'))
}

func ptrFrame(frame frameRecord) *frameRecord { return &frame }

func collectFrameErrors(frame *executiontracer.CallFrame, errors *[]string) {
	if frame.ReturnError != nil {
		*errors = append(*errors, fmt.Sprintf("%s@%s: %s", frame.ToContractName, frame.ToAddress.Hex(), frame.ReturnError.Error()))
	}
	for _, child := range frame.ChildCallFrames() {
		collectFrameErrors(child, errors)
	}
}

func verifyTargetState(caseName string, testChain *chain.TestChain, target common.Address, targetABI abi.ABI, deployed map[common.Address]*contracts.Contract, element *calls.CallSequenceElement, from common.Address) map[string]any {
	switch caseName {
	case "BeeStorage":
		args, err := targetABI.Methods["act_actor_topUp"].Inputs.Unpack(element.Call.Data[4:])
		if err != nil || len(args) < 2 {
			return map[string]any{"established": false, "error": fmt.Sprintf("解析 topUp 参数失败: %v", err)}
		}
		batchID, ok := args[1].([32]byte)
		if !ok {
			return map[string]any{"established": false, "error": "topUp batchId 未解码为 bytes32"}
		}
		var stampAddress common.Address
		var stampContract *contracts.Contract
		for address, contract := range deployed {
			if contract.Name() == "PostageStamp" {
				stampAddress, stampContract = address, contract
				break
			}
		}
		if stampContract == nil {
			return map[string]any{"established": false, "error": "Medusa 部署结果中未找到 PostageStamp"}
		}
		getter := stampContract.CompiledContract().Abi.Methods["batchNormalisedBalance"]
		packed, err := stampContract.CompiledContract().Abi.Pack(getter.Name, batchID)
		if err != nil {
			return map[string]any{"established": false, "error": err.Error()}
		}
		msg := &calls.CallMessage{From: from, To: &stampAddress, Nonce: testChain.State().GetNonce(from), Value: big.NewInt(0), GasLimit: 12_500_000, GasPrice: big.NewInt(0), GasFeeCap: big.NewInt(0), GasTipCap: big.NewInt(0), Data: packed}
		result, err := testChain.CallContract(msg.ToCoreMessage(), nil)
		if err != nil || result.Failed() {
			return map[string]any{"established": false, "getter": "PostageStamp.batchNormalisedBalance(bytes32)", "error": errorText(err)}
		}
		values, err := stampContract.CompiledContract().Abi.Unpack(getter.Name, result.Return())
		if err != nil || len(values) == 0 {
			return map[string]any{"established": false, "getter": getter.Sig, "error": errorText(err)}
		}
		value := fmt.Sprint(values[0])
		return map[string]any{"established": value == "2", "getter": "PostageStamp.batchNormalisedBalance(bytes32)", "contract_address": stampAddress.Hex(), "batch_id": "0x" + hex.EncodeToString(batchID[:]), "actual_value": value, "expected_value": "2", "event_seen": eventSeenWithContract(element, stampContract, "BatchTopUp")}
	case "Immutable":
		args, err := targetABI.Methods["approve"].Inputs.Unpack(element.Call.Data[4:])
		if err != nil || len(args) < 2 {
			return map[string]any{"established": false, "error": fmt.Sprintf("解析 approve 参数失败: %v", err)}
		}
		spender, ok := args[0].(common.Address)
		if !ok {
			return map[string]any{"established": false, "error": "approve spender 未解码为 address"}
		}
		tokenID, ok := args[1].(*big.Int)
		if !ok {
			return map[string]any{"established": false, "error": "approve tokenId 未解码为 uint256"}
		}
		values, err := runGetterAt(testChain, target, targetABI, from, "getApproved", tokenID)
		if err != nil || len(values) == 0 {
			return map[string]any{"established": false, "getter": "getApproved(uint256)", "error": errorText(err)}
		}
		actual, ok := values[0].(common.Address)
		if !ok {
			return map[string]any{"established": false, "getter": "getApproved(uint256)", "error": "getter 返回值不是 address"}
		}
		return map[string]any{"established": actual == spender, "getter": "getApproved(uint256)", "actual_value": actual.Hex(), "expected_value": spender.Hex(), "token_id": tokenID.String(), "approval_event_seen": eventSeenWithContract(element, element.Contract, "Approval")}
	}
	return map[string]any{"established": false, "error": "未知案例"}
}

func eventSeenWithContract(element *calls.CallSequenceElement, contract *contracts.Contract, name string) bool {
	results := element.ChainReference.MessageResults()
	if results == nil || results.Receipt == nil || contract == nil {
		return false
	}
	event, ok := contract.CompiledContract().Abi.Events[name]
	if !ok {
		return false
	}
	return oneEvent(results.Receipt, event)
}

func errorText(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

// Compile-time assertions catch incompatible API changes if this driver is upgraded.
var _ = (*core.ExecutionResult)(nil)
var _ = crypto.Keccak256Hash
