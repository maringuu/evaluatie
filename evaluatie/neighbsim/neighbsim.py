
import msgspec
import networkx as nx
import sqlalchemy as sa
from networkx.algorithms.bipartite.matching import minimum_weight_full_matching

from evaluatie import data
from evaluatie import models as m


class NeighBSimResult(msgspec.Struct, frozen=True):
    class TargetFunctionComparison(msgspec.Struct, frozen=True):
        target_function_id: list[int]
        tcallers: list[int]
        tcallees: list[int]

    max_dist: int

    query_binary_id: int
    target_binary_id: int

    qcallers: list[int]
    qcallees: list[int]

    #: A graph mapping the edges
    similarity_graph: nx.Graph

    target_function_id2comparision: dict[int, TargetFunctionComparison]


def _call_graph_from_binary_id(binary_id: int, session):
    SrcFunction = sa.orm.aliased(m.Function)
    DstFunction = sa.orm.aliased(m.Function)

    edges_stmt = (
        sa.select(
            m.CallGraphEdge.src_id,
            m.CallGraphEdge.dst_id,
        )
        .join(
            SrcFunction,
            m.CallGraphEdge.src,
        )
        .join(
            DstFunction,
            m.CallGraphEdge.dst,
        )
        .where(
            SrcFunction.binary_id == binary_id,
            # Note that we deliberatly ignore functions that are not in the binary.
            # XXX Should not be relevant, should it?!
            DstFunction.binary_id == binary_id,
        )
    )
    nodes_stmt = sa.select(
        m.Function,
    ).where(
        m.Function.binary_id == binary_id,
    )

    edges = session.execute(edges_stmt)
    nodes = session.scalars(nodes_stmt)

    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    graph.add_nodes_from(
        [
            (
                node.id,
                {
                    "size": node.size,
                    "name": node.name,
                },
            )
            for node in nodes
        ]
    )

    return graph


def _reachable_nodes(call_graph: nx.DiGraph, source: int, max_dist: int):
    return list(
        nx.dfs_preorder_nodes(
            call_graph,
            source=source,
            depth_limit=max_dist,
        )
    )

class NeighBSimArgs(msgspec.Struct, frozen=True):
    similarity_graph: nx.Graph

    query_binary: m.Binary
    query_call_graph: nx.DiGraph

    target_binary: m.Binary
    target_call_graph: nx.DiGraph

    @classmethod
    def from_binary_pair(cls, binary_pair: data.BinaryPair):
        with m.Session() as session:
            query_binary = binary_pair.lbinary
            target_binary = binary_pair.rbinary
            return cls(
                query_binary=query_binary,
                target_binary=target_binary,
                query_call_graph=_call_graph_from_binary_id(query_binary.id, session),
                target_call_graph=_call_graph_from_binary_id(target_binary.id, session),
                similarity_graph=binary_pair.similarity_graph,
            )


def _match_sum(left, right, similarity_graph):
    if len(left) == 0:
        return 0
    if len(right) == 0:
        return 0

    graph = similarity_graph.subgraph(left + right)

    m = minimum_weight_full_matching(graph, top_nodes=left)

    ret = 0
    for edge in m.items():
        ret += graph.edges[edge]["weight"]

    return ret


def neighbsim(query_function_id, target_function_id, args: NeighBSimArgs, max_dist=1) -> float:
    qcg = args.query_call_graph
    tcg = args.target_call_graph
    sg = args.similarity_graph
    del args

    qcallers = _reachable_nodes(
        qcg,
        query_function_id,
        max_dist=max_dist,
    )
    tcallers = _reachable_nodes(
        tcg,
        target_function_id,
        max_dist=max_dist,
    )
    qcallees = _reachable_nodes(
        qcg.reverse(copy=False),
        query_function_id,
        max_dist=max_dist,
    )
    tcallees = _reachable_nodes(
        tcg.reverse(copy=False),
        target_function_id,
        max_dist=max_dist,
    )

    # We remove from the callers only to still give some weight for recursive functions.
    try:
        qcallers.remove(query_function_id)
    except ValueError:
        pass

    try:
        tcallers.remove(target_function_id)
    except ValueError:
        pass

    # try:
    #     qcallees.remove(query_function_id)
    # except ValueError:
    #     pass

    # try:
    #     tcallees.remove(target_function_id)
    # except ValueError:
    #     pass

    ret = 0
    ret += _match_sum(qcallers, tcallers, sg)
    ret += _match_sum(qcallees, tcallees, sg)
    ret += sg.get_edge_data(query_function_id, target_function_id)["weight"]
    ret *= 2

    ret /= 2 + len(qcallers) + len(tcallers) + len(qcallees) + len(tcallees)

    return -ret
