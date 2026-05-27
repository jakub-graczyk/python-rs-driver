import asyncio
import logging
from ipaddress import IPv4Address

from scylla.batch import Batch
from scylla.enums import Consistency
from scylla.execution_profile import ExecutionProfile
from scylla.policies import HostFilter, Peer
from scylla.session_builder import SessionBuilder
from scylla.statement import Statement

logger = logging.getLogger(__name__)


class CustomHostFilter(HostFilter):
    def accept(self, peer: Peer) -> bool:
        peer_addr_ipv4 = peer.address[0]

        assert isinstance(peer_addr_ipv4, IPv4Address)

        # Accept only loopback nodes for this demo
        return peer_addr_ipv4.is_loopback


logging.basicConfig(
    level=10,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    session = await SessionBuilder().contact_points([("127.0.0.2", 9042)]).host_filter(CustomHostFilter()).connect()

    print("Connected to local Scylla cluster")

    table_name = "example_table"
    schema = "id int PRIMARY KEY, value text"

    await session.execute("""
    CREATE KEYSPACE IF NOT EXISTS example_ks
    WITH replication = {
        'class': 'NetworkTopologyStrategy',
        'replication_factor': 1
    };
    """)

    await session.execute("USE example_ks;")

    await session.execute(f"DROP TABLE IF EXISTS {table_name};")

    await session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {schema}
        );
        """
    )

    print(f"Table '{table_name}' ready")

    prepared_insert = await session.prepare(Statement(f"INSERT INTO {table_name} (id, value) VALUES (?, ?)"))

    prepared_insert = prepared_insert.with_execution_profile(
        ExecutionProfile(
            timeout=10,
            consistency=Consistency.All,
        )
    )

    print("Prepared insert statement created")

    values = [
        (0, "first natural number"),
        (1, "identity element of group Z with * as multiplication"),
        (2, "almost e"),
    ]

    await asyncio.gather(*[session.execute(prepared_insert, value) for value in values])

    print("Async inserts completed")

    batch_values = [
        (3, "almost pi"),
        (4, "composite"),
        (5, "prime"),
    ]

    batch_statement = Batch()

    batch_statement.add_all(items=[(prepared_insert, value) for value in batch_values])

    await session.batch(batch_statement)

    print("Batch insert completed")

    prepared_select = await session.prepare(f"SELECT * FROM {table_name}")

    prepared_select = prepared_select.with_page_size(1).with_consistency(Consistency.One)

    print("Prepared select statement created")

    page_result = await session.execute(prepared_select)

    print("Manual paging")

    while page_result:
        for row in page_result.iter_current_page():
            print(row)
        page_result = await page_result.fetch_next_page()

    result = await session.execute(prepared_select)

    print("Async paging")

    async for row in result:
        print(row)

    keyspace = session.cluster_state.get_keyspace("example_ks")
    table = keyspace.tables.get(table_name)

    print(table.columns)
    print(keyspace.strategy)

    cluster_state = session.cluster_state
    print(cluster_state.nodes_info.values())

    replica_locator = cluster_state.replica_locator

    token = cluster_state.compute_token("example_ks", table_name, [0])

    primary_replica = replica_locator.primary_replica_for_token(token, keyspace.strategy, "example_ks", table_name)

    node, shard = primary_replica

    print(f"Node: {node}")
    print(f"Shard: {shard}")


if __name__ == "__main__":
    asyncio.run(main())
