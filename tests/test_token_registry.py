from gmgn_twitter_intel.pipeline.token_registry import TokenRegistryEntry, TokenResolver
from gmgn_twitter_intel.storage.lancedb_client import build_lancedb_client
from gmgn_twitter_intel.storage.token_registry_repository import TokenRegistryRepository


class FakeProvider:
    def search(self, query: str):
        return [
            TokenRegistryEntry(
                chain="eth",
                ca="0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                symbol="PEPE",
                name="Pepe",
                aliases=["PEPE"],
                source="fake",
            ),
            TokenRegistryEntry(
                chain="base",
                ca="0x6982508145454Ce325dDbE47a25d4ec3d2311934",
                symbol="PEPE",
                name="Base Pepe",
                aliases=["PEPE"],
                source="fake",
            ),
        ]


def test_token_resolver_returns_ambiguous_symbol_candidates_and_persists_registry(tmp_path):
    repo = TokenRegistryRepository(build_lancedb_client(tmp_path / "twitter_intel.lancedb", embedding_dim=8))
    resolver = TokenResolver(repo, FakeProvider())

    result = resolver.resolve_symbol("PEPE")

    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert len(repo.find_by_symbol("PEPE")) == 2
    repo.close()
