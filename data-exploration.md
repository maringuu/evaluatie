<!--
SPDX-FileCopyrightText: 2024 Marten Ringwelski
SPDX-FileContributor: Marten Ringwelski <git@maringuu.de>

SPDX-License-Identifier: AGPL-3.0-only
-->
# Data Exploration
This file is a collection of interesting non-trivial cypher/sql statements
that are part of data exploration.

```cypher
// How many connected components are there in a call-graph of a specific binary.
MATCH (b:Binary {md5: "8cd3bb36a8749ea678ace71e30321532"})
MATCH (f:Function)-[:BELONGS_TO]->(b)
MATCH p=(f:Function)-[:CALLS]->(:Function)
WITH project(p) AS cg
CALL weakly_connected_components.get(cg)
YIELD node, component_id
RETURN count(DISTINCT component_id);
```

```cypher
// Get the call-graph for each binary
MATCH (b:Binary)
CALL {
  WITH b
  MATCH (f:Function)-[:BELONGS_TO]->(b)
  MATCH p=(f:Function)-[:CALLS]->(:Function)
  WITH project(p) AS cg
  RETURN cg
}
WITH cg WHERE size(cg.nodes) > 0
RETURN size(cg.nodes);
``` 

```cypher
// Get the number of connected-components of all call-graphs.

MATCH (b:Binary)
CALL {
  WITH b
  MATCH (f:Function)-[:BELONGS_TO]->(b)
  MATCH p=(f:Function)-[:CALLS]->(:Function)
  WITH project(p) AS cg
  WITH cg WHERE size(cg.nodes) > 0
  RETURN cg
}
CALL weakly_connected_components.get(cg)
YIELD node, component_id
WITH b, collect(component_id) AS component_ids
CALL {
  WITH component_ids
  UNWIND component_ids AS component_id
  RETURN count(DISTINCT component_id) AS component_count
}
RETURN b, component_count

// Does not work.
// https://github.com/memgraph/mage/issues/429
// "Procedure 'weakly_connected_components.get' did not yield all fields as required by its signature."
MATCH (b:Binary)
CALL {
  WITH b
  MATCH (f:Function)-[:BELONGS_TO]->(b)
  MATCH p=(f:Function)-[:CALLS]->(:Function)
  WITH project(p) AS cg
  WITH cg WHERE size(cg.nodes) > 0
  RETURN cg
}
CALL {
  WITH cg
  CALL weakly_connected_components.get(cg)
  YIELD node, component_id
  RETURN count(DISTINCT component_id) as component_count
}
RETURN component_count
```

```cypher
// List all recursive functions
MATCH (f:Function)-[:CALLS]->(f)
RETURN f
```

```cypher
// Get all equivalent functions
MATCH (p:Package)-[:CONTAINS]->(b:Binary)<-[:BELONGS_TO]-(f:Function)
// This effectifly works like a GROUP BY in sql.
WITH b.name as binary_name, p, f.lineno AS lineno, f.file AS function_file, f.name AS name, collect(f) AS functions
RETURN p, binary_name, size(functions) AS size, functions
ORDER BY size DESC
LIMIT 10
```

```cypher
// Why creating edges for equivalent functions is not feasible.
// Or is it?!
// Note that a set of equivalent functions would be a clique.
MATCH (p:Package)-[:CONTAINS]->(b:Binary)<-[:BELONGS_TO]-(f:Function)
WITH b.name as binary_name, p, f.lineno AS lineno, f.file AS function_file, f.name AS name, collect(f) AS functions
CALL {
  WITH functions
  RETURN size(functions) * size(functions) AS edge_count
}
RETURN sum(edge_count)
```

```cypher
// Creating a cross architecture dataset
MATCH (p:Package)-[:CONTAINS]->(b:Binary)<-[:BELONGS_TO]-(f:Function),
(b)-[:COMPILED_WITH]->(arch:Architecture {bitness: 64})
WHERE arch.name IN ["arm", "mips"]
WITH b.name as binary_name, p, f.lineno AS lineno, f.file AS function_file, collect(f) AS functions
RETURN binary_name, sum(size(functions))
```

