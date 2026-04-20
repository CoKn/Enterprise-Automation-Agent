# this file owns the reflection logic to create new procedural knowlage
import json
from typing import Optional

from agent.application.usecases.prompt_rendering import render_prompt
from agent.domain.agent import Agent
from agent.domain.context import Context, Node, NodeType, NodeStatus
from agent.domain.prompts.react.reflection_prompt import REFLECTION_PROMPT
from agent.logger import get_logger


logger = get_logger(__name__)


def has_ancestor_in_set(node: Node, ancestor_ids: set[str]) -> bool:
    current = node.parent
    while current is not None:
        if str(current.id) in ancestor_ids:
            return True
        current = current.parent
    return False


def query_existing_procedural(agent_session: Agent, goal: str) -> Optional[Context]:
    filter = {"collection": "nodes_value", "n_results": 1, "max_distance": 0.2}
    return agent_session.memory.query(goal, filter=filter, memory_type="procedural")


def clone_subtree(node: Node) -> Node:
    clone = Node(
        value=node.value,
        node_status=NodeStatus.pending,
        node_type=node.node_type,
        cached=node.cached,
        preconditions=list(node.preconditions or []),
        effects=list(node.effects or []),
        tool_name=node.tool_name,
        tool_args=dict(node.tool_args) if isinstance(node.tool_args, dict) else None,
        annotation=node.annotation,
        tool_response=None,
        tool_response_summary=None,
        next=None,
        previous=None,
    )

    clone_children: list[Node] = []
    for child in node.children:
        child_clone = clone_subtree(child)
        child_clone.parent = clone
        clone_children.append(child_clone)
    clone.children = clone_children

    return clone


def add_reference_annotation(node: Node, reference_root: Node) -> None:
    reference_hint = (
        f"Reference existing procedural plan: id={reference_root.id}, goal='{reference_root.value}'"
    )
    if node.annotation:
        if reference_hint in node.annotation:
            return
        node.annotation = f"{node.annotation}\n{reference_hint}"
    else:
        node.annotation = reference_hint


def clean_reflected_context(context: Context) -> None:
    """Clean up reflected context to enforce reflection rules.
    
    - Remove tool_response_summary from all nodes
    - Mark as fully_planned only nodes with BOTH tool_name AND tool_args
    - Ensure all nodes have status = pending
    """
    context.rebuild_indexes()
    
    for node in context.node_index.values():
        # Remove tool response summary
        node.tool_response_summary = None
        
        # Keep status as pending
        node.node_status = NodeStatus.pending
        
        # Re-classify node type: fully_planned requires BOTH tool_name and tool_args
        if node.node_type == NodeType.fully_planned:
            has_tool_name = bool(node.tool_name and str(node.tool_name).strip())
            has_tool_args = isinstance(node.tool_args, dict) and len(node.tool_args) > 0
            
            if not (has_tool_name and has_tool_args):
                # Downgrade to partially_planned if missing either tool_name or tool_args
                node.node_type = NodeType.parcially_planned

            if not has_tool_name:
                node.node_type = NodeType.abstract


def save_distilled_procedural(agent_session: Agent, procedural_context: Context) -> dict[str, int]:
    procedural_context.rebuild_indexes()

    abstract_nodes: list[Node] = []
    for root in procedural_context.roots:
        for node in procedural_context.bfs_nodes(root):
            if node.node_type == NodeType.abstract:
                abstract_nodes.append(node)

    if not abstract_nodes:
        metadata = agent_session.memory.save(context=procedural_context, memory_type="procedural")
        saved_nodes = int((metadata or {}).get("nodes_value", 0))
        saved_subtrees = len(procedural_context.roots) if saved_nodes > 0 else 0
        return {
            "saved_subtrees": saved_subtrees,
            "reused_subtrees": 0,
            "saved_nodes": saved_nodes,
        }

    # pass 1: detect duplicates against existing procedural memory before saving anything
    existing_matches: dict[str, Node] = {}
    for node in abstract_nodes:
        existing_context = query_existing_procedural(agent_session=agent_session, goal=node.value)
        existing_root = existing_context.get_root() if existing_context else None
        if existing_root and existing_root.value.strip().lower() == node.value.strip().lower():
            existing_matches[str(node.id)] = existing_root

    # pass 2: apply reference/save decisions using the precomputed duplicate view.
    handled_abstract_ids: set[str] = set()
    reused = 0
    saved = 0
    saved_nodes = 0

    for node in abstract_nodes:
        node_id = str(node.id)
        if has_ancestor_in_set(node=node, ancestor_ids=handled_abstract_ids):
            continue

        if node_id in existing_matches:
            existing_root = existing_matches[node_id]
            add_reference_annotation(node=node, reference_root=existing_root)
            reused += 1
            handled_abstract_ids.add(node_id)
            continue

        # Save a detached clone of the subtree so it can be reused as a standalone procedural plan.
        subtree_root = clone_subtree(node)
        subtree_root.parent = None
        subtree_context = Context(roots=[subtree_root])
        metadata = agent_session.memory.save(context=subtree_context, memory_type="procedural")
        saved += 1
        handled_abstract_ids.add(node_id)
        saved_nodes += int((metadata or {}).get("nodes_value", 0))

    return {
        "saved_subtrees": saved,
        "reused_subtrees": reused,
        "saved_nodes": saved_nodes,
    }


async def reflect(agent_session: Agent):
    if not agent_session.global_goal_node:
        return None

    full_context_tree = agent_session.planner.serializer.serialize_context(agent_session.context)

    reflection_prompt_rendered = render_prompt(
        agent_session=agent_session,
        template=REFLECTION_PROMPT,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "full_context_tree": json.dumps(full_context_tree),
        },
    )

    llm_result = agent_session.llm.call(
        prompt=reflection_prompt_rendered,
        json_mode=True,
    )

    if llm_result.get("error"):
        raise RuntimeError(llm_result["error"])

    logger.info(
        "LLM usage phase=reflect prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        llm_result.get("prompt_tokens", 0),
        llm_result.get("completion_tokens", 0),
        llm_result.get("total_tokens", 0),
    )

    agent_session.record_llm_usage(
        phase="reflect",
        llm_result=llm_result,
    )

    result: str = llm_result.get("response") or ""

    try:
        reflection_payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Reflection LLM did not return valid JSON: {result}") from exc

    procedural_context = agent_session.planner.serializer.deserialize_context(reflection_payload)
    if procedural_context is None:
        raise ValueError("Reflection result did not contain a valid context tree")

    procedural_context.rebuild_indexes()
    
    # Enforce reflection rules on deserialized context
    clean_reflected_context(procedural_context)
    
    agent_session.memory_context = procedural_context

    persistence_stats = save_distilled_procedural(
        agent_session=agent_session,
        procedural_context=procedural_context,
    )

    logger.info(
        "Reflection produced procedural tree with %s nodes (saved_subtrees=%s, reused_subtrees=%s, saved_nodes=%s)",
        len(procedural_context.node_index),
        persistence_stats["saved_subtrees"],
        persistence_stats["reused_subtrees"],
        persistence_stats["saved_nodes"],
    )

    return procedural_context