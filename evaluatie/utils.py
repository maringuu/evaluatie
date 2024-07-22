
import networkx as nx
import sqlalchemy as sa

from evaluatie import models as m


def call_graph_from_binary_id(binary_id: int, session: m.Session) -> nx.DiGraph:
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
        -- We deliberatly ignore extern and .plt functions as their vector is NULL
        -- and we leave this as future work.
        WHERE f.binary_id = {binary_id} AND f.section NOT IN ('extern', '.plt')
        """
    )

    cg = nx.DiGraph()

    for node, name, size in session.execute(nodes_stmt):
        cg.add_node(node, name=name, size=size)

    for src_id, dst_id in session.execute(edges_stmt):
        # Ignore edges that have nodes that we want to ignore
        if src_id not in cg or dst_id not in cg:
            continue
        cg.add_edge(src_id, dst_id)

    return cg


def similarity_graph_from_pair(qb_id: int, tb_id: int, session: m.Session, evaluation_only: bool = False) -> nx.Graph:
    """Returns the similarity graph of all functions that can have a similarity
    (i.e. the ones that have a non, null vector)
    """
    # We need to use e."function:all" here since we need to calculate similarity between all functions
    # in the call-graph, not just the functions that we use in our evaluation.

    table = "function" if evaluation_only else "function:all"

    stmt = sa.text(
        f"""
WITH qf AS (
	SELECT *
	FROM e."{table}" f
	WHERE f.binary_id = {qb_id}
),
tf AS (
	SELECT *
	FROM e."{table}" f
	WHERE f.binary_id = {tb_id}
)
SELECT qf.id AS qf_id, tf.id AS tf_id, COALESCE((lshvector_compare(qf.vector, tf.vector)).sim, 0) AS bsim
FROM qf, tf
"""
    )

    g = nx.Graph()
    g.add_weighted_edges_from(session.execute(stmt))

    return g

def similarity_graph_from_pair2(qb_id: int, tb_id: int, dataset_name: str, session: m.Session) -> nx.Graph:
    stmt = sa.text(
    f"""
WITH qf AS (
	SELECT DISTINCT ON (f.id) f.id, f.binary_id, f.vector
	FROM d."{dataset_name}"
		-- outer join to not omit functions that do not have callers/callees
		LEFT OUTER JOIN e.call_graph_edge qcg ON (
			query_function_id = qcg.src_id OR
			query_function_Id = qcg.dst_id
		)
		JOIN e."function:all" f ON (
			f.id = query_function_id OR
			f.id = qcg.src_id OR
			f.id = qcg.dst_id
		)
	WHERE query_binary_id = {qb_id}
),
tf AS (
	SELECT DISTINCT ON (f.id) f.id, f.binary_id, f.vector
	FROM d."{dataset_name}"
		LEFT OUTER JOIN e.call_graph_edge tcg ON (
			ptarget_function_id = tcg.src_id OR
			ptarget_function_id = tcg.dst_id OR
			ntarget_function_id = tcg.src_id OR
			ntarget_function_id = tcg.dst_id
		)
		JOIN e."function:all" f ON (
			f.id = ptarget_function_id OR
			f.id = ntarget_function_id OR
			f.id = tcg.src_id OR
			f.id = tcg.dst_id
		)
	WHERE target_binary_id = {tb_id}
)
SELECT qf.id, tf.id, COALESCE((lshvector_compare(qf.vector, tf.vector)).sim, 0) AS bsim
FROM qf, tf;
    """)

    g = nx.Graph()
    g.add_weighted_edges_from(session.execute(stmt))

    return g
