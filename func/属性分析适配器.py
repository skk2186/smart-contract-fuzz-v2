#!/usr/bin/env python3
"""以 Slither 的分析结果构造逐属性的、带证据的交易前提图。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from crytic_compile import CryticCompile
from crytic_compile.crytic_compile import get_platforms
from crytic_compile.platform.solc import Solc
from slither import Slither
from slither.analyses.data_dependency.data_dependency import is_dependent
from slither.core.declarations import Function
from slither.core.cfg.node import NodeType
from slither.core.variables.state_variable import StateVariable
from slither.slithir.operations import HighLevelCall, InternalCall, LibraryCall, LowLevelCall, SolidityCall
from slither.slithir.operations.index import Index


def name(function: Any) -> str:
    owner = getattr(getattr(function, "contract_declarer", None), "name", None)
    owner = owner or getattr(getattr(function, "contract", None), "name", "?")
    return f"{owner}.{getattr(function, 'full_name', getattr(function, 'name', '?'))}"


def location(item: Any) -> str:
    source = getattr(item, "source_mapping", None)
    return str(source) if source is not None else "unknown"


def unique(values: Any) -> list[str]:
    return sorted({str(value) for value in values})


def state_id(variable: Any) -> str:
    return str(getattr(variable, "canonical_name", str(variable)))


def unique_states(values: Any) -> list[str]:
    return sorted({state_id(value) for value in values})


def source_index_accesses(expression: Any) -> list[str]:
    """保留源码表达式中的索引写法；精确别名判断仍须求解。"""
    source = str(expression or "")
    accesses: list[str] = []
    for match in re.finditer(r"[A-Za-z_][\w.]*\[", source):
        depth = 0
        for pos in range(match.end() - 1, len(source)):
            if source[pos] == "[":
                depth += 1
            elif source[pos] == "]":
                depth -= 1
                if depth == 0:
                    accesses.append(source[match.start():pos + 1])
                    break
    return sorted(set(accesses))


def partial_property(function: Any, exc: Exception) -> dict[str, Any]:
    try:
        read_states = unique_states(function.all_state_variables_read())
    except Exception:
        read_states = []
    return {
        "property": name(function), "source": location(function),
        "read_states": read_states, "candidate_actions": [],
        "cross_contract": {
            "observations": [], "candidate_actions": [],
            "unmatched_observations": [], "unresolved_observations": [],
            "alias_unproven_observations": [], "opaque_call_candidates": [],
        },
        "analysis_class": "dependency_unknown", "analysis_status": "partial",
        "unknowns": [f"属性分析中断: {type(exc).__name__}: {exc}"],
    }


class PropertyAdapter:
    def __init__(
        self,
        slither: Slither,
        contract: Any,
        target: str,
        remaps: str | None,
        solc: str | None,
        compile_options: list[str],
        prefix: str,
        max_call_depth: int,
        max_setup_depth: int,
        max_paths: int,
    ) -> None:
        self.slither = slither
        self.contract = contract
        self.target = target
        self.analysis_options = {
            "solc": solc, "solc_remaps": remaps,
            "compile_options": compile_options, "property_prefix": prefix,
            "max_call_depth": max_call_depth,
            "max_setup_depth": max_setup_depth, "max_paths": max_paths,
        }
        self.prefix = prefix
        self.max_call_depth = max_call_depth
        self.max_setup_depth = max_setup_depth
        self.max_paths = max_paths
        self.unknowns: set[str] = set()
        self.entries = sorted(
            [f for f in self.contract.functions_entry_points if not f.is_constructor], key=name
        )
        self.properties = [
            f for f in self.entries
            if f.name.startswith(prefix) and len(f.parameters) == 0
            and len(f.returns) == 1 and str(f.returns[0].type) == "bool"
        ]
        invalid_properties = [
            f for f in self.entries if f.name.startswith(prefix) and f not in self.properties
        ]
        for invalid in invalid_properties:
            self.unknowns.add(f"属性签名不符合零参数、返回 bool: {name(invalid)}")
        self.actions = [
            f for f in self.entries
            if not f.name.startswith(prefix) and not f.view and not f.pure
        ]
        self.paths: dict[Any, list[list[tuple[Any, Any | None]]]] = {}
        self.path_truncated: set[str] = set()
        self.effect_cache: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
        self.effect_catalog: dict[str, dict[str, Any]] = {}
        self.external_call_cache: dict[Any, list[dict[str, Any]]] = {}
        self.opaque_call_cache: dict[Any, list[dict[str, Any]]] = {}
        for action in self.actions:
            self.paths[action] = self._call_paths(action)
        self.writers: dict[Any, set[Any]] = defaultdict(set)
        for action, paths in self.paths.items():
            for path in paths:
                function = path[-1][0]
                for variable in function.state_variables_written:
                    self.writers[variable].add(action)

    def _edges(self, function: Any) -> list[tuple[Any, Any | None]]:
        edges: list[tuple[Any, Any | None]] = []
        for modifier in function.modifiers:
            if isinstance(modifier, Function):
                edges.append((modifier, None))
        for ir in function.internal_calls + function.library_calls:
            if isinstance(ir.function, Function):
                edges.append((ir.function, ir))
        return edges

    def _call_paths(self, root: Any) -> list[list[tuple[Any, Any | None]]]:
        paths: list[list[tuple[Any, Any | None]]] = []
        stack: list[list[tuple[Any, Any | None]]] = [[(root, None)]]
        while stack:
            path = stack.pop()
            paths.append(path)
            if len(paths) >= self.max_paths:
                self.path_truncated.add(name(root))
                break
            function = path[-1][0]
            edges = self._edges(function)
            for callee, ir in reversed(edges):
                if callee in (frame[0] for frame in path):
                    self.path_truncated.add(name(root))
                elif len(path) >= self.max_call_depth:
                    self.path_truncated.add(name(root))
                else:
                    stack.append(path + [(callee, ir)])
        return paths

    @staticmethod
    def _reaches(start: Any, goal: Any) -> bool:
        todo = [start]
        seen: set[Any] = set()
        while todo:
            node = todo.pop()
            if node == goal:
                return True
            if node not in seen:
                seen.add(node)
                todo.extend(node.sons)
        return False

    @staticmethod
    def _index_accesses(node: Any) -> list[dict[str, str]]:
        return [
            {
                "base": str(ir.variable_left),
                "key": str(ir.variable_right),
                "reference": str(ir.lvalue),
            }
            for ir in node.irs if isinstance(ir, Index)
        ]

    def _raw_return_paths(self, function: Any, destination: Any) -> list[list[str]]:
        """避免递归解释谓词；只展示返回值之前的源码分支。"""
        if function.entry_point is None:
            return []
        paths: list[list[str]] = []
        pending = [(function.entry_point, [], frozenset())]
        while pending and len(paths) < self.max_paths:
            current, conditions, visited = pending.pop()
            if current in visited:
                continue
            if current == destination:
                paths.append(conditions)
                continue
            visited = visited | {current}
            if current.type in (NodeType.IF, NodeType.IFLOOP) and len(current.sons) == 2:
                for son, branch in ((current.son_false, "false"), (current.son_true, "true")):
                    if son is not None and self._reaches(son, destination):
                        pending.append((son, conditions + [f"{current.expression}: {branch}"], visited))
            else:
                if any("require(" in str(ir) or "assert(" in str(ir)
                       for ir in current.irs if isinstance(ir, SolidityCall)):
                    conditions = conditions + [str(current.expression)]
                for son in current.sons:
                    if self._reaches(son, destination):
                        pending.append((son, conditions, visited))
            if len(pending) > self.max_paths * 4:
                self.unknowns.add(f"谓词返回路径展开达到上限: {name(function)}")
                break
        return paths

    def _predicate_context(self, node: Any) -> tuple[set[Any], list[str], list[str], list[str], list[dict[str, Any]]]:
        """沿守卫调用展开状态读取；外部调用只记录，不猜测返回值。"""
        states = set(node.state_variables_read)
        calls: set[str] = set()
        external: set[str] = set()
        logic: set[str] = set()
        returns: list[dict[str, Any]] = []
        pending = [ir.function for ir in node.irs
                   if isinstance(ir, (InternalCall, LibraryCall)) and isinstance(ir.function, Function)]
        seen: set[Any] = set()
        while pending:
            function = pending.pop()
            if function in seen:
                continue
            seen.add(function)
            calls.add(name(function))
            states.update(function.state_variables_read)
            if len(seen) > self.max_paths:
                self.unknowns.add("守卫内部调用展开达到上限")
                break
            for callee, _ in self._edges(function):
                if callee not in seen:
                    pending.append(callee)
            for inner_node in function.nodes:
                if inner_node.type in (NodeType.IF, NodeType.IFLOOP, NodeType.RETURN):
                    if inner_node.expression is not None:
                        logic.add(f"{name(function)}: {inner_node.expression}")
                if inner_node.type == NodeType.RETURN:
                    returns.append({
                        "function": name(function),
                        "result_expression": str(inner_node.expression),
                        "branch_paths": self._raw_return_paths(function, inner_node),
                        "source": location(inner_node),
                    })
                for ir in inner_node.irs:
                    if isinstance(ir, (HighLevelCall, LowLevelCall)):
                        external.add(f"{name(function)}: {ir}")
        return states, sorted(calls), sorted(external), sorted(logic), returns

    def _guard(self, function: Any, node: Any, kind: str, branch: str | None) -> dict[str, Any]:
        states, predicate_calls, external, predicate_logic, predicate_returns = self._predicate_context(node)
        variables = list(node.variables_read)
        dependencies: dict[str, list[str]] = {}
        for variable in variables:
            sources: list[str] = []
            for source in list(function.parameters) + list(states):
                try:
                    if is_dependent(variable, source, function):
                        sources.append(str(source))
                except (KeyError, TypeError, AttributeError, AssertionError):
                    self.unknowns.add(f"数据依赖无法判断: {name(function)} {variable}")
            if sources:
                dependencies[str(variable)] = unique(sources)
        return {
            "kind": kind,
            "function": name(function),
            "expression": str(node.expression or node),
            "branch": branch,
            "state_reads": unique_states(states),
            "variables_read": unique(variables),
            "data_dependencies": dependencies,
            "predicate_calls": predicate_calls,
            "predicate_logic": predicate_logic,
            "predicate_returns": predicate_returns,
            "external_calls": external,
            "source": location(node),
        }

    def _guards_to(self, function: Any, destination: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for node in function.nodes:
            if node == destination:
                continue
            if node not in destination.dominators:
                continue
            if len(node.sons) == 2 and node.expression is not None:
                reaches = [self._reaches(son, destination) for son in node.sons]
                if reaches.count(True) == 1:
                    branch = "true" if reaches[0] else "false"
                    result.append(self._guard(function, node, "control_branch", branch))
                elif reaches.count(True) == 2:
                    # 两条分支均可到达写入点，不能把该条件称为必要前提。
                    continue
            elif any("require(" in str(ir) or "assert(" in str(ir)
                     for ir in node.irs if isinstance(ir, SolidityCall)):
                result.append(self._guard(function, node, "require_or_assert", None))
        return result

    def _cfg_alternatives(self, function: Any, destination: Any) -> tuple[list[list[dict[str, Any]]], bool]:
        """枚举有限条 CFG 简单路径；每条路径保留条件分支和 require。"""
        if function.entry_point is None:
            return [], False
        alternatives: list[list[dict[str, Any]]] = []
        stack: list[tuple[Any, list[dict[str, Any]], frozenset[Any]]] = [
            (function.entry_point, [], frozenset())
        ]
        truncated = False
        while stack:
            node, guards, visited = stack.pop()
            if node in visited:
                continue
            if node == destination:
                alternatives.append(guards)
                if len(alternatives) >= self.max_paths:
                    truncated = bool(stack)
                    break
                continue
            next_visited = visited | {node}
            if any("require(" in str(ir) or "assert(" in str(ir)
                   for ir in node.irs if isinstance(ir, SolidityCall)):
                guards = guards + [self._guard(function, node, "require_or_assert", None)]
            if node.type in (NodeType.IF, NodeType.IFLOOP) and len(node.sons) == 2:
                for son, branch in ((node.son_false, "false"), (node.son_true, "true")):
                    if son is not None and self._reaches(son, destination):
                        stack.append((son, guards + [self._guard(function, node, "control_branch", branch)],
                                      next_visited))
            else:
                for son in reversed(node.sons):
                    if self._reaches(son, destination):
                        stack.append((son, guards, next_visited))
            if len(stack) + len(alternatives) > self.max_paths * 4:
                truncated = True
                break
        return alternatives, truncated

    def _modifier_guards(self, function: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for modifier in function.modifiers:
            if not isinstance(modifier, Function):
                continue
            placeholders = [node for node in modifier.nodes if node.type == NodeType.PLACEHOLDER]
            if not placeholders:
                self.unknowns.add(f"修饰器未找到函数体占位点: {name(modifier)}")
                continue
            if len(placeholders) > 1:
                self.unknowns.add(f"修饰器包含多个函数体占位点: {name(modifier)}")
            result.extend(self._guards_to(modifier, placeholders[0]))
        return result

    @staticmethod
    def _bindings(function: Any, incoming: Any | None) -> dict[str, str]:
        if incoming is None or not hasattr(incoming, "arguments"):
            return {}
        return {
            str(parameter) or f"arg_{index}": str(argument)
            for index, (parameter, argument) in enumerate(zip(function.parameters, incoming.arguments))
        }

    def _site_context(self, path: list[tuple[Any, Any | None]], write_node: Any) -> dict[str, Any]:
        guards: list[dict[str, Any]] = []
        alternatives: list[dict[str, Any]] = []
        for i, (function, _) in enumerate(path):
            guards.extend(self._modifier_guards(function))
            for modifier in function.modifiers:
                if isinstance(modifier, Function):
                    placeholders = [n for n in modifier.nodes if n.type == NodeType.PLACEHOLDER]
                    if placeholders:
                        modifier_paths, truncated = self._cfg_alternatives(modifier, placeholders[0])
                        alternatives.append({
                            "function": name(modifier), "paths": modifier_paths,
                            "truncated": truncated,
                        })
            incoming_next = path[i + 1][1] if i < len(path) - 1 else None
            destination = write_node if i == len(path) - 1 else (
                incoming_next.node if incoming_next is not None else None
            )
            if destination is not None:
                guards.extend(self._guards_to(function, destination))
                cfg_paths, truncated = self._cfg_alternatives(function, destination)
                alternatives.append({
                    "function": name(function), "paths": cfg_paths,
                    "truncated": truncated,
                })
                if truncated:
                    self.unknowns.add(f"CFG 路径展开达到上限: {name(function)}")
        deduped = {json.dumps(g, sort_keys=True, ensure_ascii=False): g for g in guards}
        external = []
        for function, _ in path:
            for node in function.nodes:
                for ir in node.irs:
                    if isinstance(ir, (HighLevelCall, LowLevelCall)):
                        external.append({"function": name(function), "call": str(ir), "source": location(node)})
        return {
            "call_path": [
                {"function": name(function), "bindings": self._bindings(function, incoming),
                 "call_source": location(incoming.node) if incoming is not None else None}
                for function, incoming in path
            ],
            "guards": list(deduped.values()),
            "cfg_guard_alternatives": alternatives,
            "external_calls_in_reachable_functions": external,
            "expression_call_constraints": self._expression_call_constraints(write_node),
        }

    def _expression_call_constraints(self, node: Any) -> list[dict[str, Any]]:
        """写入值所依赖的内部/库函数也可能因 require 回滚。"""
        result: list[dict[str, Any]] = []
        pending: list[tuple[Any, Any, int]] = [
            (ir.function, ir, 0) for ir in node.irs
            if isinstance(ir, (InternalCall, LibraryCall)) and isinstance(ir.function, Function)
        ]
        seen: set[Any] = set()
        while pending:
            function, incoming, depth = pending.pop()
            if function in seen:
                continue
            seen.add(function)
            if depth >= self.max_call_depth:
                self.unknowns.add(f"表达式内部调用展开达到上限: {name(function)}")
                continue
            endpoints = [n for n in function.nodes if n.type == NodeType.RETURN]
            if not endpoints:
                endpoints = [n for n in function.nodes if not n.sons and n.type != NodeType.THROW]
            alternatives: list[list[dict[str, Any]]] = []
            truncated = False
            for endpoint in endpoints:
                paths, hit_limit = self._cfg_alternatives(function, endpoint)
                alternatives.extend(paths)
                truncated |= hit_limit
            result.append({
                "function": name(function),
                "bindings": self._bindings(function, incoming),
                "successful_return_guard_paths": alternatives[:self.max_paths],
                "truncated": truncated or len(alternatives) > self.max_paths,
                "source": location(incoming.node),
            })
            for inner_node in function.nodes:
                for ir in inner_node.irs:
                    if isinstance(ir, (InternalCall, LibraryCall)) and isinstance(ir.function, Function):
                        pending.append((ir.function, ir, depth + 1))
        return result

    def _effects(self, action: Any, variable: Any) -> list[dict[str, Any]]:
        cache_key = (action, variable)
        if cache_key in self.effect_cache:
            return self.effect_cache[cache_key]
        effects: dict[str, dict[str, Any]] = {}
        for path in self.paths[action]:
            function = path[-1][0]
            for node in function.nodes:
                if variable not in node.state_variables_written:
                    continue
                context = self._site_context(path, node)
                effect = {
                    "state": state_id(variable), "writer": name(function),
                    "expression": str(node.expression or node),
                    "index_accesses": self._index_accesses(node),
                    "source_index_accesses": source_index_accesses(node.expression),
                    "source": location(node), **context,
                }
                effect_id = self._register_effect(effect)
                effects[effect_id] = self.effect_catalog[effect_id]
        self.effect_cache[cache_key] = list(effects.values())
        return self.effect_cache[cache_key]

    def _register_effect(self, effect: dict[str, Any]) -> str:
        serialized = json.dumps(effect, sort_keys=True, ensure_ascii=False)
        effect_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        effect["id"] = effect_id
        self.effect_catalog[effect_id] = effect
        return effect_id

    def _typed_call_paths(self, root: Any) -> list[dict[str, Any]]:
        """沿 Slither 已解析的内部调用、修饰器和高层调用展开有限条路径。"""
        if root in self.external_call_cache:
            return self.external_call_cache[root]
        calls: list[dict[str, Any]] = []
        opaque: list[dict[str, Any]] = []
        pending = deque([(root, [], None, (), frozenset())])
        while pending and len(calls) < self.max_paths:
            function, prefix, incoming, route, visited = pending.popleft()
            if function in visited:
                continue
            for local_path in self._call_paths(function):
                local_path = list(local_path)
                local_path[0] = (function, incoming)
                path = prefix + local_path
                if len(path) > self.max_call_depth:
                    self.path_truncated.add(name(root))
                    continue
                caller = local_path[-1][0]
                for node in caller.nodes:
                    for ir in node.irs:
                        if isinstance(ir, LowLevelCall):
                            if len(opaque) < self.max_paths:
                                opaque.append({
                                    "caller": name(caller), "call": str(ir),
                                    "source": location(node),
                                    "external_route": list(route),
                                    "reason": "低层调用的目标状态写入无法由 Slither 静态解析",
                                })
                            else:
                                self.path_truncated.add(name(root))
                            continue
                        if not isinstance(ir, HighLevelCall):
                            continue
                        step = {
                            "caller": name(caller), "receiver": str(ir.destination),
                            "source": location(node),
                        }
                        item = {
                            "path": path, "call": ir, "route": route + (step,),
                            "receiver": str(ir.destination),
                            "receiver_scope": getattr(caller.contract, "name", "?"),
                        }
                        calls.append(item)
                        target = ir.function
                        if (not isinstance(target, (Function, StateVariable))
                                or isinstance(target, Function) and not target.nodes):
                            if len(opaque) < self.max_paths:
                                opaque.append({
                                    "caller": name(caller), "call": str(ir),
                                    "source": location(node),
                                    "external_route": list(item["route"]),
                                    "reason": "高层调用缺少可解析的目标函数体",
                                })
                            else:
                                self.path_truncated.add(name(root))
                        if (isinstance(target, Function) and target.nodes
                                and target not in visited
                                and target not in (frame[0] for frame in path)
                                and len(path) < self.max_call_depth):
                            pending.append((target, path, ir, item["route"],
                                            visited | {frame[0] for frame in path}))
                        if len(calls) >= self.max_paths:
                            self.path_truncated.add(name(root))
                            break
                    if len(calls) >= self.max_paths:
                        break
                if len(calls) >= self.max_paths:
                    break
        self.external_call_cache[root] = calls
        self.opaque_call_cache[root] = opaque
        return calls

    @staticmethod
    def _external_state_variables(ir: Any, access: str) -> list[Any]:
        target = ir.function
        if isinstance(target, StateVariable):
            return [target] if access == "read" else []
        if isinstance(target, Function) and target.nodes:
            return (target.all_state_variables_read() if access == "read"
                    else target.all_state_variables_written())
        return []

    def _typed_effects(self, item: dict[str, Any], variable: Any) -> list[dict[str, Any]]:
        """只把已解析目标函数中的实际写入点登记为 effect。"""
        effects: dict[str, dict[str, Any]] = {}
        call = item["call"]
        if not isinstance(call.function, Function):
            return []
        for target_path in self._call_paths(call.function):
            target_path = list(target_path)
            target_path[0] = (call.function, call)
            target_function = target_path[-1][0]
            for node in target_function.nodes:
                if variable not in node.state_variables_written:
                    continue
                context = self._site_context(item["path"] + target_path, node)
                effect = {
                    "state": state_id(variable), "receiver": item["receiver"],
                    "receiver_scope": item["receiver_scope"],
                    "external_route": list(item["route"]),
                    "writer": name(target_function),
                    "expression": str(node.expression or node),
                    "index_accesses": self._index_accesses(node),
                    "source_index_accesses": source_index_accesses(node.expression),
                    "source": location(node), **context,
                    "resolution": "Slither 已解析目标写入点；对象别名与执行可达性未证明。",
                }
                effect_id = self._register_effect(effect)
                effects[effect_id] = self.effect_catalog[effect_id]
        return list(effects.values())

    def _cross_contract_context(self, prop: Any) -> dict[str, Any]:
        observations: list[dict[str, Any]] = []
        scoped_reads: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        unresolved: list[dict[str, Any]] = []
        for item in self._typed_call_paths(prop):
            call = item["call"]
            states = self._external_state_variables(call, "read")
            observation = {
                "receiver": item["receiver"],
                "receiver_scope": item["receiver_scope"],
                "external_route": list(item["route"]),
                "target": name(call.function) if isinstance(call.function, Function) else str(call.function),
                "read_states": unique_states(states),
                "call": str(call), "source": location(call.node),
                "resolution": ("resolved_body" if states else
                               "stateless_target" if isinstance(call.function, Function)
                               and call.function.nodes else "unresolved_target"),
            }
            observations.append(observation)
            if states:
                for state in states:
                    scoped_reads[state].append(observation)
            elif observation["resolution"] == "unresolved_target":
                unresolved.append(observation)
        candidates = []
        prerequisite_states: dict[tuple[str, str], dict[str, Any]] = {}
        matched_states: set[Any] = set()
        exact_states: set[Any] = set()
        for action in self.actions:
            action_matches: list[tuple[dict[str, Any], Any, str]] = []
            for item in self._typed_call_paths(action):
                for state in self._external_state_variables(item["call"], "write"):
                    if state not in scoped_reads:
                        continue
                    same_receiver = any(
                        obs["receiver"] == item["receiver"]
                        and obs["receiver_scope"] == item["receiver_scope"]
                        for obs in scoped_reads[state]
                    )
                    relation = ("same_static_receiver" if same_receiver else
                                "state_overlap_alias_unproven")
                    action_matches.append((item, state, relation))
            if not action_matches:
                continue
            matched_states.update(state for _, state, _ in action_matches)
            exact_states.update(state for _, state, relation in action_matches
                                if relation == "same_static_receiver")
            effects: list[dict[str, Any]] = []
            for item, state, _ in action_matches:
                effects.extend(self._typed_effects(item, state))
            for effect in effects:
                for guard in effect["guards"]:
                    for guard_state in guard["state_reads"]:
                        root_contracts = {self.contract.name} | {
                            inherited.name for inherited in self.contract.inheritance
                        }
                        guard_owner = guard["function"].split(".", 1)[0]
                        scope = "self" if guard_owner in root_contracts else effect["receiver"]
                        key = (scope, guard_state)
                        prerequisite_states[key] = {
                            "receiver": scope, "state": guard_state,
                            "target_entrypoint_writers": sorted({
                                name(function)
                                for contract in self.slither.contracts
                                for function in contract.functions_entry_points
                                if any(state_id(v) == guard_state
                                       for v in function.all_state_variables_written())
                            }),
                            "note": "可选的状态建立函数；调用权限和对象别名需另行验证。",
                        }
            candidates.append({
                "function": name(action),
                "matched_observations": [
                    {"receiver": item["receiver"],
                     "receiver_scope": item["receiver_scope"],
                     "external_route": list(item["route"]),
                     "state": state_id(state), "relation": relation,
                     "property_calls": sorted({o["call"] for o in scoped_reads[state]})}
                    for item, state, relation in action_matches
                ],
                "effect_ids": sorted({e["id"] for e in effects}),
                "status": ("target_write_site_unresolved" if not effects else
                           "direct_static_candidate" if all(r == "same_static_receiver"
                                                            for _, _, r in action_matches)
                           else "alias_unproven_candidate"),
                "slither_conditional_state_reads": unique_states(
                    action.all_conditional_state_variables_read()),
                "slither_is_protected_hint": action.is_protected(),
            })
        if unresolved:
            self.unknowns.add(f"{name(prop)}: 部分外部属性读取无法解析到目标状态")
        unmatched = [
            {"state": state_id(state),
             "property_calls": sorted({o["call"] for o in observations})}
            for state, observations in scoped_reads.items()
            if state not in matched_states
        ]
        alias_unproven = [
            {"state": state_id(state),
             "property_calls": sorted({o["call"] for o in observations})}
            for state, observations in scoped_reads.items()
            if state in matched_states and state not in exact_states
        ]
        if unmatched:
            self.unknowns.add(f"{name(prop)}: 部分外部状态读取未找到解析后的写入入口")
        if alias_unproven:
            self.unknowns.add(f"{name(prop)}: 存在仅按状态变量重叠关联的候选，对象别名未证明")
        opaque_actions = [
            {"function": name(action),
             "calls": self.opaque_call_cache.get(action, []),
             "status": "opaque_effect_possible_no_property_link"}
            for action in self.actions if self.opaque_call_cache.get(action)
        ]
        return {
            "observations": observations,
            "opaque_property_calls": self.opaque_call_cache.get(prop, []),
            "candidate_actions": candidates,
            "prerequisite_states": list(prerequisite_states.values()),
            "unresolved_observations": unresolved,
            "unmatched_observations": unmatched,
            "alias_unproven_observations": alias_unproven,
            "opaque_call_candidates": opaque_actions[:self.max_paths],
            "opaque_candidates_truncated": len(opaque_actions) > self.max_paths,
            "matching_rule": "按 Slither 解析出的目标状态变量关联；接收者不一致时只列为别名未证明候选。",
        }

    def _read_sites(self, property_function: Any) -> list[dict[str, Any]]:
        sites: dict[str, dict[str, Any]] = {}
        for path in self._call_paths(property_function):
            function = path[-1][0]
            for node in function.nodes:
                if not node.state_variables_read:
                    continue
                item = {
                    "function": name(function),
                    "states": unique_states(node.state_variables_read),
                    "expression": str(node.expression or node),
                    "index_accesses": self._index_accesses(node),
                    "source_index_accesses": source_index_accesses(node.expression),
                    "source": location(node),
                }
                sites[json.dumps(item, sort_keys=True, ensure_ascii=False)] = item
        return list(sites.values())

    def _setup_closure(self, initial_states: set[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        todo = deque((state, 0) for state in initial_states)
        seen: set[Any] = set()
        while todo:
            state, depth = todo.popleft()
            if state in seen:
                continue
            seen.add(state)
            writers = sorted(self.writers.get(state, set()), key=name)
            entry: dict[str, Any] = {
                "state": state_id(state), "depth": depth,
                "declaration_initializer": str(state.expression) if state.expression is not None else None,
                "constructor_writers": sorted({
                    name(function)
                    for contract in [self.contract] + list(self.contract.inheritance)
                    for function in contract.functions
                    if function.is_constructor and state in function.all_state_variables_written()
                }),
                "possible_setup_actions": [],
                "note": "当前状态可能已满足条件；这些写入函数是可选建立路径，并非必需交易。",
            }
            if depth >= self.max_setup_depth:
                entry["truncated"] = True
                self.unknowns.add(f"前置状态展开达到上限: {state}")
            else:
                for writer in writers:
                    effects = self._effects(writer, state)
                    entry["possible_setup_actions"].append({
                        "function": name(writer),
                        "effect_ids": [effect["id"] for effect in effects],
                    })
                    for effect in effects:
                        for guard in effect["guards"]:
                            for guard_state in guard["state_reads"]:
                                for actual in self.writers:
                                    if state_id(actual) == guard_state and actual not in seen:
                                        todo.append((actual, depth + 1))
            result.append(entry)
        return result

    def analyze_property(self, prop: Any) -> dict[str, Any]:
        prior_unknowns = set(self.unknowns)
        read_states = set(prop.all_state_variables_read())
        cross_contract = self._cross_contract_context(prop)
        balance_observations = [
            {"function": name(function), "operation": str(ir), "source": location(node)}
            for path in self._call_paths(prop)
            for function in [path[-1][0]]
            for node in function.nodes for ir in node.irs
            if isinstance(ir, SolidityCall) and "balance(address)" in str(ir)
        ]
        candidates = []
        prerequisite_states: set[Any] = set()
        for action in self.actions:
            shared = sorted(read_states.intersection(action.all_state_variables_written()), key=str)
            if not shared:
                continue
            effects = [effect for variable in shared for effect in self._effects(action, variable)]
            for effect in effects:
                for guard in effect["guards"]:
                    for state in self.writers:
                        if state_id(state) in guard["state_reads"]:
                            prerequisite_states.add(state)
            candidates.append({
                "function": name(action),
                "payable": bool(action.payable),
                "environment_reads": unique(action.all_solidity_variables_read()),
                "matched_states": unique_states(shared),
                "effect_ids": [effect["id"] for effect in effects],
                "analysis_status": "candidate_only" if effects else "no_write_site_found",
            })
        has_candidate = bool(candidates or cross_contract["candidate_actions"])
        resolved_effect_links = sum(bool(c["effect_ids"]) for c in candidates)
        resolved_effect_links += sum(bool(c["effect_ids"])
                                     for c in cross_contract["candidate_actions"])
        if not has_candidate and (read_states or cross_contract["observations"]):
            self.unknowns.add(f"{name(prop)}: 未找到可改变所读状态的已解析外部入口")
        direct_candidates = {candidate["function"] for candidate in candidates}
        unresolved_effect_actions = []
        for action in self.actions:
            if name(action) in direct_candidates:
                continue
            external_calls = [str(ir) for _, ir in action.all_high_level_calls()]
            external_calls += [str(ir) for ir in action.all_low_level_calls()]
            assembly = any(node.type == NodeType.ASSEMBLY for node in action.all_nodes())
            if external_calls or assembly:
                unresolved_effect_actions.append({
                    "function": name(action),
                    "external_calls": sorted(set(external_calls)),
                    "inline_assembly": assembly,
                    "reason": "无已解析的直接写入；外部调用、回调或汇编可能产生未建模影响。",
                })
        setup_closure = self._setup_closure(prerequisite_states)
        unknowns = set(self.unknowns) - prior_unknowns
        if unresolved_effect_actions:
            unknowns.add("部分入口的外部调用或汇编效果未闭合；直接读写候选集合可能漏掉间接影响")
        if balance_observations:
            unknowns.add("属性观察合约原生币余额；外部转入、强制转入及部署余额需要执行环境确认")
        if any(site["index_accesses"] for site in self._read_sites(prop)):
            unknowns.add("mapping/数组索引别名未求解；共享基础状态变量仅代表保守候选")
        if prop.all_high_level_calls() or prop.all_low_level_calls():
            unknowns.add("属性自身含外部调用；其读取结果取决于实际部署与调用环境")
        if cross_contract["candidate_actions"]:
            unknowns.add("跨合约候选的对象别名、调用结果和执行可达性仍需验证")
        if cross_contract["opaque_property_calls"]:
            unknowns.add("属性自身含无法静态解析的调用；状态依赖可能不完整")
        if any(self.effect_catalog[effect_id]["external_calls_in_reachable_functions"]
               for candidate in candidates for effect_id in candidate["effect_ids"]):
            unknowns.add("候选调用链含外部调用；静态输出未证明其返回值或副作用")
        if any(any(node.type == NodeType.IFLOOP for node in function.nodes)
               for candidate in candidates
               for action in self.actions if name(action) == candidate["function"]
               for path in self.paths[action] for function, _ in path):
            unknowns.add("候选调用链含循环；CFG 仅枚举无重复节点的路径")
        if any(any(node.type == NodeType.ASSEMBLY for node in function.nodes)
               for candidate in candidates
               for action in self.actions if name(action) == candidate["function"]
               for path in self.paths[action] for function, _ in path):
            unknowns.add("候选调用链含内联汇编；相关数据流可能不完整")
        if (name(prop) in self.path_truncated or any(
                c["function"] in self.path_truncated for c in candidates)
                or any(c["function"] in self.path_truncated
                       for c in cross_contract["candidate_actions"])
                or any(c["function"] in self.path_truncated
                       for c in cross_contract["opaque_call_candidates"])):
            unknowns.add("调用路径受深度或数量上限截断")
        if any(g["external_calls"] for c in candidates
               for effect_id in c["effect_ids"]
               for g in self.effect_catalog[effect_id]["guards"]):
            unknowns.add("守卫含外部调用，返回值和副作用需结合部署环境确认")
        return {
            "property": name(prop), "source": location(prop),
            "read_states": unique_states(read_states),
            "environment_reads": unique(prop.all_solidity_variables_read()),
            "balance_observations": balance_observations,
            "read_sites": self._read_sites(prop),
            "candidate_actions": candidates,
            "cross_contract": cross_contract,
            "evidence_summary": {
                "candidate_links": len(candidates) + len(cross_contract["candidate_actions"]),
                "links_with_write_site": resolved_effect_links,
                "alias_unproven_links": sum(
                    c["status"] == "alias_unproven_candidate"
                    for c in cross_contract["candidate_actions"]),
                "unmatched_observations": len(cross_contract["unmatched_observations"]),
                "opaque_call_candidates": len(cross_contract["opaque_call_candidates"]),
            },
            "analysis_class": (
                "stateful_context_available" if has_candidate else
                "stateful_dependency_unresolved" if read_states or any(
                    obs["read_states"] for obs in cross_contract["observations"]) else
                "dependency_unknown" if cross_contract["unresolved_observations"]
                or cross_contract["opaque_property_calls"] else
                "stateless_or_input_only"
            ),
            "analysis_status": "analyzed",
            "unresolved_effect_actions": unresolved_effect_actions,
            "prerequisite_state_closure": setup_closure,
            "unknowns": sorted(unknowns),
            "interpretation": "静态候选和必要守卫；不证明路径可行、参数可满足或属性可被违反。",
        }

    def run(self) -> dict[str, Any]:
        if not self.properties:
            self.unknowns.add(f"没有找到零参数、以 {self.prefix!r} 开头的显式属性")
        properties = []
        for prop in self.properties:
            try:
                properties.append(self.analyze_property(prop))
            except Exception as exc:
                properties.append(partial_property(prop, exc))
        return {
            "schema_version": "2.0",
            "input": {"target": self.target, "contract": self.contract.name,
                      "slither_version": importlib.metadata.version("slither-analyzer"),
                      "analysis_options": self.analysis_options},
            "properties": properties,
            "effect_catalog": dict(sorted(self.effect_catalog.items())),
            "global_unknowns": sorted(self.unknowns),
        }


def _build_compile_kwargs(args: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"skip_clean": True}
    if args.solc_remaps:
        kwargs["solc_remaps"] = args.solc_remaps
    if args.solc:
        kwargs["solc"] = args.solc
    for item in args.compile_option:
        if "=" not in item:
            raise ValueError(f"编译选项应为 NAME=VALUE: {item}")
        key, value = item.split("=", 1)
        kwargs[key.lstrip("-").replace("-", "_")] = value
    return kwargs


def _framework_root(target: str) -> tuple[str | None, str | None]:
    """用 Crytic Compile 的平台探测规则寻找源码所属项目。"""
    path = Path(target).resolve()
    for ancestor in (path if path.is_dir() else path.parent, *path.parents):
        if not ancestor.is_dir():
            continue
        for platform in get_platforms():
            if issubclass(platform, Solc):
                continue
            try:
                if platform.is_supported(str(ancestor)):
                    locate_root = getattr(platform, "locate_project_root", None)
                    if locate_root is not None:
                        located = locate_root(str(path))
                        if located is not None:
                            return str(located), platform.NAME
                    return str(ancestor), platform.NAME
            except (OSError, ValueError):
                continue
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Solidity 文件或可由 crytic-compile 构建的项目目录")
    parser.add_argument("--contract", help="目标合约名；省略时分析所有含显式属性的合约")
    parser.add_argument("--contract-source", help="合约同名时按源码路径片段筛选")
    parser.add_argument("--project-root", help="覆盖自动探测的项目根目录")
    parser.add_argument("--output", required=True, help="输出 JSON 路径")
    parser.add_argument("--solc-remaps", help="传递给 solc 的空格分隔导入映射")
    parser.add_argument("--solc", help="solc 可执行文件路径")
    parser.add_argument("--compile-option", action="append", default=[],
                        help="额外 crytic-compile 参数 NAME=VALUE，可重复")
    parser.add_argument("--property-prefix", default="echidna_", help="显式属性函数名前缀")
    parser.add_argument("--max-call-depth", type=int, default=12)
    parser.add_argument("--max-setup-depth", type=int, default=3)
    parser.add_argument("--max-paths", type=int, default=1000)
    args = parser.parse_args()
    if min(args.max_call_depth, args.max_setup_depth + 1, args.max_paths) < 1:
        parser.error("分析上限必须为正数")
    output = Path(args.output)
    project_root, detected_framework = _framework_root(args.target)
    if args.project_root:
        project_root, detected_framework = str(Path(args.project_root).resolve()), "user_selected"
    report: dict[str, Any] = {
        "schema_version": "2.0", "status": "compilation_failed",
        "input": {"target": args.target, "contract": args.contract,
                  "project_root": project_root, "detected_framework": detected_framework,
                  "compile_options": args.compile_option,
                  "slither_version": importlib.metadata.version("slither-analyzer"),
                  "crytic_compile_version": importlib.metadata.version("crytic-compile")},
        "contracts_discovered": [], "contracts_analyzed": [],
        "properties": [], "effect_catalog": {}, "global_unknowns": [],
        "contract_issues": [], "errors": [],
    }
    try:
        kwargs = _build_compile_kwargs(args)
        if project_root and Path(args.target).is_file():
            kwargs["cwd"] = project_root
        compiled = CryticCompile(args.target, **kwargs)
        report["input"]["compilation_platform"] = compiled.platform.NAME
        slither = Slither(compiled)
        report["contracts_discovered"] = [
            {"name": c.name, "source": location(c)} for c in slither.contracts
        ]
        contracts = [c for c in slither.contracts
                     if (args.contract is None or c.name == args.contract)
                     and (args.contract_source is None or args.contract_source in location(c))]
        if args.contract is None:
            contracts = [c for c in contracts if any(
                f.name.startswith(args.property_prefix) for f in c.functions_entry_points)]
        if not contracts:
            report["status"] = "no_matching_contract_or_property"
            report["global_unknowns"].append("未找到符合筛选条件的属性合约；已保留发现的合约列表")
        else:
            for contract in contracts:
                report["contracts_analyzed"].append(
                    {"name": contract.name, "source": location(contract)})
                try:
                    adapter = PropertyAdapter(
                        slither, contract, args.target, args.solc_remaps, args.solc,
                        args.compile_option, args.property_prefix, args.max_call_depth,
                        args.max_setup_depth, args.max_paths)
                    part = adapter.run()
                    report["properties"].extend(part["properties"])
                    report["effect_catalog"].update(part["effect_catalog"])
                    report["global_unknowns"].extend(part["global_unknowns"])
                except Exception as exc:
                    report["contract_issues"].append({
                        "contract": contract.name, "source": location(contract),
                        "type": type(exc).__name__, "message": str(exc),
                    })
                    report["properties"].extend(
                        partial_property(prop, exc)
                        for prop in contract.functions_entry_points
                        if prop.name.startswith(args.property_prefix))
            report["global_unknowns"] = sorted(set(report["global_unknowns"]))
            report["status"] = ("partial" if report["contract_issues"] or any(
                p["analysis_status"] == "partial" for p in report["properties"]) else
                                "complete" if report["properties"] else
                                "no_matching_property")
    except Exception as exc:
        report["status"] = "compilation_or_analysis_failed"
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"分析状态 {report['status']}，属性 {len(report['properties'])} 条，结果: {output}")
    for prop in report["properties"]:
        print(f"  {prop['property']}: 自身状态 {len(prop['candidate_actions'])} 个候选，"
              f"跨合约 {len(prop['cross_contract']['candidate_actions'])} 个候选，"
              f"分类 {prop['analysis_class']}，状态 {prop['analysis_status']}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
