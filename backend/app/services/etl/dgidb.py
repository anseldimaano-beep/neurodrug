import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings


class DGIdbClient:
    """DGIdb v5 GraphQL client (the old REST v2 API is deprecated)."""

    GRAPHQL_URL = "https://dgidb.org/api/graphql"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_interactions(self, genes: list = None, drugs: list = None, interaction_types: list = None):
        gene_list = genes or []
        # GraphQL query for DGIdb v5
        query = """
        query GetInteractions($genes: [String!]!) {
          genes(names: $genes) {
            nodes {
              name
              interactions {
                drug {
                  name
                  approved
                }
                interactionScore
                interactionTypes {
                  type
                  directionality
                }
                publications {
                  pmid
                }
              }
            }
          }
        }
        """
        payload = {"query": query, "variables": {"genes": gene_list}}
        response = await self.client.post(
            self.GRAPHQL_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        interactions = []
        nodes = data.get("data", {}).get("genes", {}).get("nodes", [])
        for node in nodes:
            gene_name = node.get("name")
            for inter in node.get("interactions", []):
                drug = inter.get("drug", {})
                drug_name = drug.get("name") if drug else None
                if not drug_name:
                    continue
                interaction_type = None
                types = inter.get("interactionTypes", [])
                if types:
                    interaction_type = types[0].get("type")
                pmids = [p.get("pmid") for p in inter.get("publications", []) if p.get("pmid")]
                interactions.append({
                    "gene_symbol": gene_name,
                    "drug_name": drug_name,
                    "interaction_type": interaction_type,
                    "pmids": pmids,
                    "score": inter.get("interactionScore"),
                })
        return interactions
