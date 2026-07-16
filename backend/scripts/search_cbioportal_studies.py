"""
Search cBioPortal's public API for studies matching a keyword, so you can
find the correct study_id before running run_cbioportal_comutation.py.
No auth required — hits the public cbioportal.org instance directly.

Usage:
    docker-compose exec api python scripts/search_cbioportal_studies.py --keyword "ewing sarcoma"
    docker-compose exec api python scripts/search_cbioportal_studies.py --keyword "medulloblastoma"
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from app.services.etl.cbioportal import CBioPortalClient


async def main(keyword: str):
    async with CBioPortalClient() as client:
        results = await client.search_studies(keyword)

    if not results:
        print(f"No studies found for '{keyword}'.")
        return

    print(f"Found {len(results)} studies matching '{keyword}':\n")
    # Sort by sample count descending — larger cohorts generally give more
    # reliable co-occurrence statistics.
    results_sorted = sorted(results, key=lambda s: s.get("allSampleCount", 0), reverse=True)
    for study in results_sorted:
        print(f"  studyId: {study.get('studyId')}")
        print(f"    name: {study.get('name')}")
        print(f"    samples: {study.get('allSampleCount')}")
        print(f"    description: {(study.get('description') or '')[:150]}")
        print()

    print("Pick the studyId that best matches your disease and cohort size, "
          "then run:\n"
          "  python scripts/run_cbioportal_comutation.py --study-id <studyId> "
          "--gene-ids <YOUR_GENE_PANEL>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.keyword))
