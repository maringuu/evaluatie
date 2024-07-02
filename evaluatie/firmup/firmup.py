
import networkx as nx
import sqlalchemy as sa

from evaluatie import models as m


def firmup(query_function_id: int, target_binary_id: int):
    session = m.Session()

    query_function = session.get(m.Function, query_function_id) 
    query_binary_id = query_function.binary_id

    similarity = sa.func.lshvector_compare(
        m.Function.vector, query_function.vector
    ).scalar_table_valued("sim")
    target_functions_stmt = (
        sa.select(
            m.Function,
            similarity,
        )
        .where(
            m.Function.binary_id == target_binary_id,
        )
        .order_by(
            sa.nullslast(similarity.desc()),
        )
    )
    matching = nx.Graph()

    tnodes = []

    for target_function, sim in session.execute(target_functions_stmt):
        # XXX Should we really use null things?!
        sim = sim or 0
        target2query_sim = sa.func.lshvector_compare(
            m.Function.vector, target_function.vector,
        ).scalar_table_valued("sim")
        
        match_counter_stmt = sa.select(
            m.Function.id,
        ).where(
            m.Function.binary_id == query_binary_id,
        ).where(
            ~m.Function.id.in_(tnodes),
        ).where(
            target2query_sim > sim,
        ).order_by(
            sa.nullslast(target2query_sim.desc()),
        ).limit(
            1,
        )
        counter_id = session.scalar(match_counter_stmt)

        if counter_id is None:
            matching.add_edge(target_function.id, query_function_id)
            break
        
        matching.add_edge(target_function.id, counter_id)
        tnodes.append(target_function.id)

    return matching
