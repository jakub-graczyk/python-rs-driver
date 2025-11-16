# ruff: noqa: F811 F401
import pytest


@pytest.mark.smoke
def test_imports():
    import scylla as X  # pyright: ignore[reportUnusedImport]
    import scylla.session as X  # pyright: ignore[reportUnusedImport]
    import scylla.session_builder as X  # pyright: ignore[reportUnusedImport]
    from scylla import session as X  # pyright: ignore[reportUnusedImport]
    from scylla import session_builder as X  # pyright: ignore[reportUnusedImport]
    from scylla.session import Session as X  # pyright: ignore[reportUnusedImport]
    from scylla.session_builder import SessionBuilder as X  # pyright: ignore[reportUnusedImport]
