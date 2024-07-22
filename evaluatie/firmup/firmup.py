
import msgspec
import networkx as nx


class FirmUPArgs(msgspec.Struct):
    similarity_graph: nx.Graph

    query_binary_id: int
    target_binary_id: int


def firmup(query_function_id: int, args: FirmUPArgs) -> nx.Graph|None:
    """Returns None if the firmup algorithm failed.
    If it succeds, it returns the matching"""
    # This implements the algorithm exactly as described in the paper

    sg = args.similarity_graph

    matching = nx.Graph()
    unmatched_stack = [(args.query_binary_id, query_function_id)]

    failed = False
    while (query_function_id not in matching) and not failed:
        modified = False
        my_binary_id, my_function_id = unmatched_stack[-1]
        other_binary_id = args.query_binary_id if my_binary_id == args.target_binary_id else args.target_binary_id

        unmatched_sg = sg.subgraph(
            # Restrict to all unmatched nodes
            [node for node in sg.nodes if node not in matching]
        )

        forward_match = _get_best_match(
            my_function_id,
            similarity_graph=unmatched_sg,
        )

        backward_match = _get_best_match(
            forward_match,
            similarity_graph=unmatched_sg,
        )

        my_stack_entry = (my_binary_id, my_function_id)
        other_stack_entry = (other_binary_id, forward_match)
        if my_function_id == backward_match:
            matching.add_edge(my_function_id, forward_match)

            try:
                unmatched_stack.remove(my_stack_entry)
            except ValueError:
                pass
            try:
                unmatched_stack.remove(other_stack_entry)
            except ValueError:
                pass
            modified = True
        else:
            if my_stack_entry not in unmatched_stack:
                unmatched_stack.append(my_stack_entry)
                modified = True
            if other_stack_entry not in unmatched_stack:
                unmatched_stack.append(other_stack_entry)
                modified = True

        failed = not modified

    if failed:
        return None

    return matching


def _get_best_match(function_id: int, similarity_graph: nx.Graph):
    return max(
        similarity_graph[function_id],
        key=lambda other_id: similarity_graph.get_edge_data(function_id, other_id)["weight"],
    )
