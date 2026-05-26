import asyncio
from ipaddress import IPv4Address

from scylla.batch import Batch
from scylla.enums import Consistency
from scylla.execution_profile import ExecutionProfile
from scylla.policies import HostFilter, Peer
from scylla.session_builder import SessionBuilder
from scylla.statement import Statement


class CustomHostFilter(HostFilter):
    def __init__(self):
        super().__init__()

    def accept(self, peer: Peer) -> bool:
        peer_addr_ipv4 = peer.address[0]
        assert isinstance(peer_addr_ipv4, IPv4Address)
        # accept only loopback nodes for demo.
        return peer_addr_ipv4.is_loopback


async def main():
    session = await SessionBuilder().contact_points([("127.0.0.2", 9042)]).host_filter(CustomHostFilter()).connect()

    # Basic query literal execution && prepare table for demo.

    table_name = "example_table"
    schema = "id int PRIMARY KEY, value text"
    await session.execute(
        "CREATE KEYSPACE IF NOT EXISTS example_ks WITH replication = {'class': 'NetworkTopologyStrategy', 'replication_factor': 3};"
    )
    await session.execute("USE example_ks;")
    await session.execute(f"DROP TABLE IF EXISTS {table_name};")
    await session.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({schema});")

    prepared_insert = await session.prepare(Statement(f"INSERT INTO {table_name} (id, value) VALUES (?, ?)"))
    prepared_insert = prepared_insert.with_execution_profile(ExecutionProfile(timeout=10, consistency=Consistency.All))

    values = [(0, "first natural number"), (1, "identity element of group Z with * as multiplication"), (2, "almost e")]

    # Insert asynchronously values using prepared statement.
    _ = await asyncio.gather(*[session.execute(prepared_insert, v) for v in values])

    batch_values = [(3, "almost pi"), (4, "composite"), (5, "prime")]

    batch_statement = Batch()
    batch_statement.add_all(items=[(prepared_insert, b_v) for b_v in batch_values])

    _ = await session.batch(batch_statement)

    prepared_select = (
        (await session.prepare(f"SELECT * FROM {table_name}")).with_page_size(1).with_consistency(Consistency.One)
    )

    page_result = await session.execute(prepared_select)

    print("Manual paging")
    while page_result:
        print("================PAGE START================")
        for row in page_result.iter_current_page():
            print(row)
        page_result = await page_result.fetch_next_page()
        print("================PAGE END================")

    result = await session.execute(prepared_select)

    print("\nAsync paging")
    async for row in result:
        print(row)


asyncio.run(main())
