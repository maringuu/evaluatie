
import msgspec
import networkx as nx

from evaluatie import models as m
from evaluatie import utils


class FirmUPArgs(msgspec.Struct):
    similarity_graph: nx.Graph

    query_binary_id: int
    target_binary_id: int

class FirmUPResult(msgspec.Struct):
    matching: nx.Graph
    steps: int

class StepLimitReachedError(Exception):
    pass


def firmup(query_function_id: int, args: FirmUPArgs, max_steps: int|None = None) -> FirmUPResult|None:
    """Returns None if the firmup algorithm failed.
    If it succeds, it returns the matching.
    Raises StepLimitReachedError if the maximum number of steps would be exceeded"""
    # This implements the algorithm exactly as described in the paper

    sg = args.similarity_graph

    # "Matches" in the paper
    matching = nx.Graph()
    # "ToMatch" in the paper.
    # We additionally store each function's binary id to identify in which direction
    # the match should be done.
    # This is needed for line 5 of the algorithm.
    unmatched_stack = [(args.query_binary_id, query_function_id)]

    n_steps = 0
    if max_steps is None:
        max_steps = float("inf")
        
    # Part of GameDidntEnd()
    failed = False
    # "A match was found for qv"
    while (query_function_id not in matching) and not failed and n_steps < max_steps:
        n_steps += 1
        modified = False
        # Impelemnts lines 4 to 8.
        # my_binary_id corresponds to "My" and other_binary_id to "Other"
        # my_function_id corresponds to "M"
        # "we try to match the procedure at the head of the ToMatch stack"
        my_binary_id, my_function_id = unmatched_stack[-1]
        other_binary_id = args.query_binary_id if my_binary_id == args.target_binary_id else args.target_binary_id

        # "we search for the best match for M in Other, while ignoring all previously matched procedures."
        unmatched_sg = sg.subgraph(
            # Restrict to all unmatched nodes
            [node for node in sg.nodes if node not in matching]
        )

        # Line 9.
        # Corresponds to "Forward".
        forward_match = _get_best_match(
            my_function_id,
            similarity_graph=unmatched_sg,
        )
        # Not mentioned in the paper.
        # Still, if all functions other_binary_id are already part of the matching,
        # there is no forwared_match as all functions are already matched.
        # We simply thread this as fail condition.
        if forward_match is None:
            failed = True
            break
        
        # Line 10.
        # Corresponds to "Back".
        backward_match = _get_best_match(
            forward_match,
            similarity_graph=unmatched_sg,
        )
        # Same check as for the forward match
        if backward_match is None:
            failed = True
            break

        my_stack_entry = (my_binary_id, my_function_id)
        forward_stack_entry = (other_binary_id, forward_match)
        backward_stack_entry = (my_binary_id, backward_match)
        # Line 11.
        # "Back is M, meaning that M ∼ Forward"
        if my_function_id == backward_match:
            matching.add_edge(my_function_id, forward_match)

            top = unmatched_stack.pop(-1)
            assert top == my_stack_entry

            # This is what the algorithm does in line 13,
            # but not what the text says.
            # According to the text only "M is popped from the stack"
            try:
                unmatched_stack.remove(forward_stack_entry)
            except ValueError:
                pass

            modified = True
        else:
            # Line 15
            if forward_stack_entry not in unmatched_stack:
                unmatched_stack.append(forward_stack_entry)
                modified = True
            # Line 15
            if backward_stack_entry not in unmatched_stack:
                unmatched_stack.append(backward_stack_entry)
                modified = True

        # "ToMatch has arrived at a fixed state."
        # "This will happen when no new procedures are pushed to ToMatch at pushIfNotExists() (line 15)"
        # According to the above this is correct, but I find this suspicions as
        # unmatched_stack.pop also modifies the stack.
        # Thus I added an additional check above.
        failed = not modified

    if n_steps >= max_steps:
        raise StepLimitReachedError

    if query_function_id not in matching:
        return None

    return FirmUPResult(
        steps=n_steps,
        matching=matching,
    )


def _get_best_match(function_id: int, similarity_graph: nx.Graph):
    if len(similarity_graph[function_id]) == 0:
        return None

    return max(
        similarity_graph[function_id],
        key=lambda other_id: similarity_graph.get_edge_data(function_id, other_id)["weight"],
    )

def firmup_args_from_binary_ids(query_binary_id: int, target_binary_id: int) -> FirmUPArgs:
    with m.Session() as session:
        similarity_graph = utils.similarity_graph_from_pair(
            qb_id=query_binary_id,
            tb_id=target_binary_id,
            session=session,
        )

    return FirmUPArgs(
        query_binary_id=query_binary_id,
        target_binary_id=target_binary_id,
        similarity_graph=similarity_graph,
    )
