import msgspec
import networkx as nx
import sqlalchemy as sa

from evaluatie import models as m


class BinaryPair(msgspec.Struct, frozen=True):
    lbinary: m.Binary
    rbinary: m.Binary

    #: A list of pairs of functions that should match
    positives: list[tuple[int, int]]
    #: A list of paris that should not match
    negatives: list[tuple[int, int]]

    # A bipartite graph where 'left' are functions from lbinary,
    # and 'right' are functions from rbinary.
    similarity_graph: nx.Graph

    @classmethod
    def from_binary_ids(cls, lid: int, rid: int):
        with m.Session() as session:
            LFunction = sa.orm.aliased(m.Function)
            RFunction = sa.orm.aliased(m.Function)
            positives_stmt = sa.select(
                LFunction.id,
                RFunction.id,
            ).where(
                LFunction.binary_id == lid,
                RFunction.binary_id == rid,
            ).where(
                LFunction.lineno == RFunction.lineno,
                LFunction.file == RFunction.file,
                LFunction.name == RFunction.name,
            ).where(
                LFunction.vector != None,
                RFunction.vector != None,
            )
            positives=list(session.execute(positives_stmt))

            negatives_stmt = sa.select(
                LFunction.id,
                RFunction.id,
            ).where(
                LFunction.binary_id == lid,
                RFunction.binary_id == rid,
            ).where(
                LFunction.lineno != RFunction.lineno,
                LFunction.file != RFunction.file,
                LFunction.name != RFunction.name,
            ).where(
                LFunction.vector != None,
                RFunction.vector != None,
            ).limit(len(positives))
            negatives=list(session.execute(negatives_stmt))

            # lfunction_ids = [id for id, _ in positives + negatives]
            # rfunction_ids = [id for _, id in positives + negatives]

            # lneighbors_stmt = sa.union(
            #     sa.select(m.CallGraphEdge.src_id).where(m.CallGraphEdge.dst_id.in_(lfunction_ids)),
            #     sa.select(m.CallGraphEdge.dst_id).where(m.CallGraphEdge.src_id.in_(lfunction_ids)),
            # )
            # rneighbors_stmt = sa.union(
            #     sa.select(m.CallGraphEdge.src_id).where(m.CallGraphEdge.dst_id.in_(rfunction_ids)),
            #     sa.select(m.CallGraphEdge.dst_id).where(m.CallGraphEdge.src_id.in_(rfunction_ids)),
            # )
            # lneighbors = list(session.scalars(lneighbors_stmt))
            # rneighbors = list(session.scalars(rneighbors_stmt))

            # all_lfunction_ids = lfunction_ids + lneighbors
            # all_rfunction_ids = rfunction_ids + rneighbors

            # similarity_stmt = sa.select(
            #     LFunction.id,
            #     RFunction.id,
            #     sa.func.lshvector_compare(LFunction.vector, RFunction.vector).scalar_table_valued("sim"),
            # ).where(
            #     # The call-graph could contain edges to other binaries (i.e. dynamically linked libraries)
            #     LFunction.binary_id == lid,
            #     RFunction.binary_id == rid,
            # ).where(
            #     LFunction.id.in_(all_lfunction_ids),
            #     RFunction.id.in_(all_rfunction_ids),
            # )
            edges = session.execute(sa.text(
                f"""SELECT lid, rid, sim
                FROM similarities
                WHERE lbinary_id = {lid} AND rbinary_id = {rid}
                """
            ))
            similarity_graph = nx.Graph()
            similarity_graph.add_weighted_edges_from([(u, v, -w) for u, v,w in edges])

            return cls(
                lbinary=session.get(m.Binary, lid),
                rbinary=session.get(m.Binary, rid),
                positives=positives,
                negatives=negatives,
                similarity_graph=similarity_graph,
            )
