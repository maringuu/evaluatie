import itertools
import pathlib as pl

import msgspec
import networkx as nx
import pandas as pd
import sqlalchemy as sa

from evaluatie import models as m


class Pair(msgspec.Struct, frozen=True):
    """A pair of functions"""

    query_binary_id: int
    query_function_id: int

    target_binary_id: int
    target_function_id: int


class DatasetSpec(msgspec.Struct, frozen=True):
    """For each build parameter, specifies if it shold vary accross
    the samples or not."""

    # XXX It would be nice if we could specify allowed combinations explicitly
    compiler_backend: bool = False
    compiler_version: bool = False
    optimisation: bool = False
    architecture: bool = False
    bitness: bool = False
    lto: bool = False
    noinline: bool = False
    pie: bool = False

    require_callers: bool = False
    require_callees: bool = False
    require_neighbors: bool = False

    # XXX This seems too compilcated to implement in sql
    #minimum_callers: int = 0
    #minimum_callees: int = 0

    positive_count: int = 1000
    negative_count: int = 1000


class Dataset(msgspec.Struct, frozen=True):
    """A dataset that is used for analysis"""

    spec: DatasetSpec

    #: A list of positive function pairs
    positives: list[Pair]
    #: A list of negative function pairs
    negatives: list[Pair]

    #: Maps tuples of binary ids to their similarity graph.
    #: The order of binary id's does not matter.
    binary_ids2similarity_graph: dict[tuple[int, int], nx.Graph]
    #: Maps binary ids to call-graphs
    binary_id2call_graph: dict[int, nx.Graph]

    @classmethod
    def from_spec(cls, spec: DatasetSpec):
        positive_df = _sample_function_pairs(
            package_name="binutils",
            package_version="2.30",
            name="objdump",
            spec=spec,
            positive=True,
            amount=spec.positive_count,
        )
        negative_df = _sample_function_pairs(
            package_name="binutils",
            package_version="2.30",
            name="objdump",
            spec=spec,
            positive=False,
            amount=spec.negative_count,
        )

        binary_pairs = (
            pd.concat(
                (positive_df, negative_df),
                axis=0,
            )
            .reset_index(
                drop=True,
            )[["qb_id", "tb_id"]]
            .drop_duplicates()
        )

        binary_ids2similarity_graph = {}
        for _, (qb_id, tb_id) in binary_pairs.iterrows():
            bsim_graph = _similarity_graph_from_pair(qb_id, tb_id)
            binary_ids2similarity_graph[(qb_id, tb_id)] = bsim_graph
            binary_ids2similarity_graph[(tb_id, qb_id)] = bsim_graph

        binary_id2call_graph = {}
        with m.Session() as session:
            for binary_id in itertools.chain(binary_pairs["qb_id"], binary_pairs["tb_id"]):
                binary_id2call_graph[binary_id] = call_graph_from_binary_id(binary_id, session)

        return cls(
            spec=spec,
            positives=_dataframe_to_pairs(positive_df),
            negatives=_dataframe_to_pairs(negative_df),
            binary_ids2similarity_graph=binary_ids2similarity_graph,
            binary_id2call_graph=binary_id2call_graph,
        )

    @classmethod
    def from_pickle(cls, path: pl.Path):
        pass

    def to_frame(self) -> pd.DataFrame:
        """Returns a dataframe of containing the positives and negatives."""
        positive_df = pd.DataFrame(
            [_pair_to_row(pair) for pair in self.positives]
        )
        positive_df["label"] = 1

        negative_df = pd.DataFrame(
            [_pair_to_row(pair) for pair in self.negatives]
        )
        negative_df["label"] = 0

        df = pd.concat(
            (positive_df, negative_df),
            axis=0,
        ).reset_index(
            drop=True,
        )

        return df
        

 

def call_graph_from_binary_id(binary_id: int, session) -> nx.DiGraph:
    edges_stmt = sa.text(
        f"""
        SELECT src_id, dst_id
        FROM v.call_graph_edge cg
        WHERE cg.src_binary_id = {binary_id}
        """
    )
    nodes_stmt = sa.text(
        f"""
        SELECT f.id, f.name, f.size
        FROM "function" f
        WHERE f.binary_id = {binary_id}
        """
    )

    cg = nx.DiGraph()

    for src_id, dst_id in session.execute(edges_stmt):
        cg.add_edge(src_id, dst_id)
    for node, name, size in session.execute(nodes_stmt):
        cg.add_node(node, name=name, size=size)

    return cg


def similarity_graph_from_pair(qb_id: int, tb_id: int) -> nx.Graph:
    """Returns the similarity graph of all functions that can have a similarity
    (i.e. the ones that have a non, null vector)
    """
    stmt = sa.text(
        f"""
WITH qf AS (
	SELECT *
	FROM "function" f
	WHERE f.binary_id = {qb_id} AND f.vector IS NOT NULL
),
tf AS (
	SELECT *
	FROM "function" f
	WHERE f.binary_id = {tb_id} AND f.vector IS NOT NULL
)
SELECT qf.id AS qf_id, tf.id AS tf_id, (lshvector_compare(qf.vector, tf.vector)).sim AS bsim
FROM qf, tf"""
    )

    g = nx.Graph()
    with m.Session() as session:
        g.add_weighted_edges_from(session.execute(stmt))
    return g


def _pair_from_row(row) -> Pair:
    return Pair(
        # Convert numpy.int64 to python integers
        query_binary_id=int(row["qb_id"]),
        query_function_id=int(row["qf_id"]),
        target_binary_id=int(row["tb_id"]),
        target_function_id=int(row["tf_id"]),
    )

def _pair_to_row(pair: Pair) -> dict:
    return {
        "qb_id": pair.query_binary_id,
        "qf_id": pair.query_function_id,
        "tb_id": pair.target_binary_id,
        "tf_id": pair.target_function_id,
    }


def _dataframe_to_pairs(df: pd.DataFrame) -> list[Pair]:
    return df.apply(_pair_from_row, axis=1).values.tolist()


def _op(varying: bool):
    if varying:
        return "!="
    else:
        return "="


def _sample_function_pairs(
    package_name: str,
    package_version: str,
    name: str,
    spec: DatasetSpec,
    positive: bool,
    amount: int,
) -> pd.DataFrame:
    """Samples the given amount of function pairs of the given software from the database.
    Only samples functions that have an associated vector."""
    if positive:
        tf_sql = """
		tf.name = qf.name AND
		tf.file = qf.file AND
		tf.lineno = qf.lineno"""
    else:
        tf_sql = """
		tf.name != qf.name OR
		tf.file != qf.file OR
		tf.lineno != qf.lineno"""

    #relevant_where = "TRUE"
    #if spec.require_callees:
    #    relevant_where += ""

    stmt = sa.text(f"""
WITH package_binary AS (
	-- All binaries from a specific software package
	SELECT *
	FROM "binary"
	WHERE (
		"name" = '{name}' AND
		package_name = '{package_name}' AND
		package_version = '{package_version}'
	) AND EXISTS (
		SELECT *
		FROM "eval-function"
		WHERE binary_id = "binary".id
	)
),
binary_w_params AS (
	-- Binaries with their build parameters
	SELECT qb.*, qbp.compiler_backend, qbp.compiler_version, qbp.optimisation, qbp.architecture, qbp.bitness, qbp.lto, qbp.noinline, qbp.pie
	FROM package_binary AS qb JOIN build_parameters qbp ON (
		qb.build_parameters_id = qbp.id
	)
),
binary_pair AS (
	-- Pairs of binaries that differ according to the requirements
	SELECT qb.id AS qb_id, tb.id AS tb_id
	FROM binary_w_params AS qb JOIN binary_w_params AS tb ON (
		qb.compiler_backend {_op(spec.compiler_backend)} tb.compiler_backend AND
		qb.compiler_version {_op(spec.compiler_version)} tb.compiler_version AND
		qb.optimisation {_op(spec.optimisation)} tb.optimisation AND
		qb.architecture {_op(spec.architecture)} tb.architecture AND
		qb.bitness {_op(spec.bitness)} tb.bitness AND
		qb.lto {_op(spec.lto)} tb.lto AND
		qb.noinline {_op(spec.noinline)} tb.noinline AND
		qb.pie {_op(spec.pie)} tb.pie AND
		-- Avoid having the same pair twice
		qb.id < tb.id
	)
),
relevant_function AS (
    SELECT f.*
    FROM binary_pair bp
        -- XXX This is probably very slow
        JOIN "eval-function" f ON (f.binary_id = bp.qb_id OR f.binary_id = bp.tb_id)
		LEFT JOIN "call_graph_edge" cg_caller ON (f.id = cg_caller.dst_id)
		LEFT JOIN "call_graph_edge" cg_callee ON (f.id = cg_callee.src_id)
    -- XXX Respect the conditions above
	WHERE (cg_caller.dst_id IS NOT NULL) OR (cg_callee.src_id IS NOT NULL)        
        
),
function_pair AS (
	-- Pairs of binaries with a query function for each pair.
	SELECT qb_id, tb_id, qf.id AS qf_id, tf.id AS tf_id
	FROM binary_pair JOIN "relevant_function" qf ON (
		qb_id = qf.binary_id
	) JOIN "relevant_function" tf ON (
		tb_id = tf.binary_id AND (
			{tf_sql}
		)
	)
	ORDER BY RANDOM()
    -- This is the number of pairs that we actually want.
    -- Note that there must not be a corresponding target function for every query function
	LIMIT {amount}
)
SELECT *
FROM function_pair
""")

    df = pd.read_sql(stmt, m.engine)
    return df


class BinaryPair(msgspec.Struct, frozen=True):
    lbinary: m.Binary
    rbinary: m.Binary

    # A bipartite graph where 'left' are functions from lbinary,
    # and 'right' are functions from rbinary.
    similarity_graph: nx.Graph

    @classmethod
    def from_binary_ids(cls, lid: int, rid: int):
        with m.Session() as session:
            LFunction = sa.orm.aliased(m.Function)
            RFunction = sa.orm.aliased(m.Function)
            positives_stmt = (
                sa.select(
                    LFunction.id,
                    RFunction.id,
                )
                .where(
                    LFunction.binary_id == lid,
                    RFunction.binary_id == rid,
                )
                .where(
                    LFunction.lineno == RFunction.lineno,
                    LFunction.file == RFunction.file,
                    LFunction.name == RFunction.name,
                )
                .where(
                    LFunction.vector != None,
                    RFunction.vector != None,
                )
            )
            positives = list(session.execute(positives_stmt))

            negatives_stmt = (
                sa.select(
                    LFunction.id,
                    RFunction.id,
                )
                .where(
                    LFunction.binary_id == lid,
                    RFunction.binary_id == rid,
                )
                .where(
                    LFunction.lineno != RFunction.lineno,
                    LFunction.file != RFunction.file,
                    LFunction.name != RFunction.name,
                )
                .where(
                    LFunction.vector != None,
                    RFunction.vector != None,
                )
                .limit(len(positives))
            )
            negatives = list(session.execute(negatives_stmt))

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
            edges = session.execute(
                sa.text(
                    f"""SELECT lid, rid, sim
                FROM similarities
                WHERE lbinary_id = {lid} AND rbinary_id = {rid}
                """
                )
            )
            similarity_graph = nx.Graph()
            similarity_graph.add_weighted_edges_from([(u, v, -w) for u, v, w in edges])

            return cls(
                lbinary=session.get(m.Binary, lid),
                rbinary=session.get(m.Binary, rid),
                positives=positives,
                negatives=negatives,
                similarity_graph=similarity_graph,
            )
