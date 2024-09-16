import msgspec
import networkx as nx
import sqlalchemy as sa
from networkx.algorithms.bipartite.matching import minimum_weight_full_matching

from evaluatie import models as m
from evaluatie.utils import call_graph_from_binary_id


class NeighBSimArgs(msgspec.Struct, frozen=True):
    """A collection of data that is needed for neighbsim score calculation."""

    #: A full bipartite graph. Left nodes are all functions from query_binary_id and
    #: right nodes are from target_binary_id.
    #: Edge weights are the bsim score.
    similarity_graph: nx.Graph

    query_binary_id: int
    query_call_graph: nx.DiGraph

    target_binary_id: int
    target_call_graph: nx.DiGraph


class NeighBSimResult(msgspec.Struct, frozen=True):
    args: "NeighBSimArgs"

    qcallers: list[int]
    tcallers: list[int]

    qcallees: list[int]
    tcallees: list[int]

    #: The callers that were matches with the corresponding weights
    caller_matching: nx.Graph
    #: The callees that were matches with the corresponding weights
    callee_matching: nx.Graph

    score: float


def _matching_graph(left: list[int], right: list[int], similarity_graph: nx.Graph):
    g = nx.Graph()
    g.add_nodes_from(left)
    g.add_nodes_from(right)

    if len(left) == 0:
        return g
    if len(right) == 0:
        return g

    mg = similarity_graph.subgraph(left + right).copy()
    for u, v, data in mg.edges(data=True):
        edge = (u, v)
        mg.edges[edge]["weight"] = -data["weight"]

    assert len(mg.edges) == len(left) * len(right), "Similarity graph is missing edges"

    m = minimum_weight_full_matching(mg, top_nodes=left)

    g.add_edges_from(m.items())
    for edge in m.items():
        g.edges[edge]["weight"] = similarity_graph.edges[edge]["weight"]

    return g


def _edge_weight_sum(graph: nx.Graph):
    return sum(data["weight"] for _, _, data in graph.edges(data=True))


def neighbsim(
    query_function_id,
    target_function_id,
    args: NeighBSimArgs,
) -> NeighBSimResult:
    qcg = args.query_call_graph
    tcg = args.target_call_graph
    sg = args.similarity_graph

    qcallers = list(
        qcg.successors(query_function_id),
    )
    tcallers = list(
        tcg.successors(target_function_id),
    )
    qcallees = list(
        qcg.reverse(copy=False).successors(query_function_id),
    )
    tcallees = list(
        tcg.reverse(copy=False).successors(target_function_id),
    )

    try:
        qcallers.remove(query_function_id)
    except ValueError:
        pass

    try:
        tcallers.remove(target_function_id)
    except ValueError:
        pass

    try:
        qcallees.remove(query_function_id)
    except ValueError:
        pass

    try:
        tcallees.remove(target_function_id)
    except ValueError:
        pass

    caller_matching = _matching_graph(qcallers, tcallers, sg)
    callee_matching = _matching_graph(qcallees, tcallees, sg)

    # fmt: off
    # Calculate the score of the matching that matches callers to callers,
    # calless to callees and the query to the target function.
    # Finally, normalize to get a score of 1, if all matches are correct.
    score = (
        # Multipy by 2 to account for the fact, that we normalize by the amount of nodes,
        # not by the amount of edges.
        # For perfectly, equal graphs, the amount of nodes would be twice the amount of edges.
        # For non-perfect graphs, this penalizes unmatched nodes.
        2 * (
            sg.get_edge_data(query_function_id, target_function_id)["weight"]
            + _edge_weight_sum(caller_matching)
            + _edge_weight_sum(callee_matching)
        ) / (
            2 +
            len(qcallers) +
            len(tcallers) +
            len(qcallees) +
            len(tcallees)
        )
    )
    # fmt: on
    return NeighBSimResult(
        args=args,
        score=score,
        callee_matching=callee_matching,
        caller_matching=caller_matching,
        qcallers=qcallers,
        tcallers=tcallers,
        qcallees=qcallees,
        tcallees=tcallees,
    )


class NeighBSimLazyArgs(msgspec.Struct):
    query_binary_id: int
    query_call_graph: nx.DiGraph

    target_binary_id: int
    target_call_graph: nx.DiGraph

    @classmethod
    def from_binary_ids(cls, query_binary_id: int, target_binary_id: int, session: m.Session):
        return cls(
            query_binary_id=query_binary_id,
            target_binary_id=target_binary_id,
            query_call_graph=call_graph_from_binary_id(query_binary_id, session),
            target_call_graph=call_graph_from_binary_id(target_binary_id, session),
        )


def neighbsim_lazy(
    query_function_id,
    target_function_id,
    args: NeighBSimLazyArgs,
    session: m.Session,
) -> NeighBSimResult:
    """A variation of our neighbsim implementation that fetches similarity lazily from the database.
    Much faster for querying few functions from a binary pair, but much slower for more functions.
    """

    query_neighbors = list(
        args.query_call_graph.to_undirected(
            as_view=True,
        ).neighbors(
            query_function_id,
        )
    )
    query_neighbors.append(query_function_id)

    target_neighbors = list(
        args.target_call_graph.to_undirected(
            as_view=True,
        ).neighbors(
            target_function_id,
        )
    )
    target_neighbors.append(target_function_id)

    # The coalesce here is not as bad as one might think.
    # As we only use functions from the ghidra call-graph (which ignores extern functions)
    stmt = sa.text(f"""
        SELECT qf.id, tf.id, COALESCE((lshvector_compare(qf.vector, tf.vector)).sim, 0)
        FROM e."function:all" qf, e."function:all" tf
        WHERE qf.id IN ({','.join(str(id) for id in query_neighbors)}) AND tf.id IN ({','.join(str(id) for id in target_neighbors)})
    """)

    sg = nx.Graph()
    for qf_id, tf_id, sim in session.execute(stmt):
        sg.add_edge(
            qf_id,
            tf_id,
            weight=sim,
        )

    return neighbsim(
        query_function_id=query_function_id,
        target_function_id=target_function_id,
        args=NeighBSimArgs(
            query_binary_id=args.query_binary_id,
            target_binary_id=args.target_binary_id,
            query_call_graph=args.query_call_graph,
            target_call_graph=args.target_call_graph,
            similarity_graph=sg,
        ),
    )
