from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime
from typing import List, Dict
from itertools import combinations
from collections import Counter, defaultdict

from app.models.domain import Drug, Disease, Gene, Protein, Interaction, DataSource, ETLJob
from app.services.etl.string import StringClient
from app.services.etl.opentargets import OpenTargetsClient
from app.services.etl.dgidb import DGIdbClient
from app.services.etl.chembl import ChEMBLClient
from app.services.etl.uniprot import UniProtClient
from app.services.etl.clinicaltrials import ClinicalTrialsClient
from app.services.etl.gdc import GDCClient
from app.services.etl.cbioportal import CBioPortalClient
from app.core.logging import logger

# ── Open Targets disease ID mapping ────────────────────────────────────────────
# OpenTargets Platform v4 accepts MONDO IDs directly — no EFO translation needed.
# MONDO IDs stored in the Disease table are passed straight to the GraphQL API.


class ETLOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, source_name: str) -> ETLJob:
        job = ETLJob(source_name=source_name, status="queued")
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def _load_job(self, job_id: int) -> ETLJob | None:
        result = await self.db.execute(select(ETLJob).where(ETLJob.id == job_id))
        return result.scalar_one_or_none()

    async def _start_job(self, job: ETLJob):
        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

    async def _finish_job(self, job: ETLJob, processed: int, inserted: int):
        job.records_processed = processed
        job.records_inserted = inserted
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        await self.db.commit()

    async def _fail_job(self, job: ETLJob, exc: Exception):
        await self.db.rollback()
        job.status = "failed"
        job.error_log = str(exc)
        job.completed_at = datetime.utcnow()
        await self.db.commit()

    async def update_datasource_status(self, name: str, status: str, records: int = 0, errors: int = 0):
        result = await self.db.execute(select(DataSource).where(DataSource.name == name))
        ds = result.scalar_one_or_none()
        if ds:
            ds.last_status = status
            ds.last_fetch_at = datetime.utcnow()
            ds.record_count = records
            ds.error_count = errors
            ds.version += 1
            await self.db.commit()

    # ── OpenTargets ────────────────────────────────────────────────────────
    async def ingest_opentargets(self, job_id: int, efo_id: str):
        # efo_id is the MONDO ID stored in Disease.efo_id.
        ot_query_id = efo_id  # MONDO IDs passed directly — OT v4 accepts them natively

        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with OpenTargetsClient() as client:
                associations = await client.get_disease_associations(ot_query_id)

            inserted = 0
            for assoc in associations:
                gene_symbol = assoc.get("gene_symbol")
                if not gene_symbol:
                    continue
                result = await self.db.execute(select(Gene).where(Gene.symbol == gene_symbol))
                gene = result.scalar_one_or_none()
                if not gene:
                    gene = Gene(symbol=gene_symbol, name=assoc.get("gene_name"),
                                biotype=assoc.get("biotype"),
                                is_oncogene=False, is_tumor_suppressor=False)
                    self.db.add(gene)
                    await self.db.flush()

                result = await self.db.execute(select(Disease).where(Disease.efo_id == efo_id))
                disease = result.scalar_one_or_none()
                if disease:
                    self.db.add(Interaction(
                        interaction_type="GeneDisease",
                        source_gene_id=gene.id,
                        disease_id=disease.id,
                        evidence_score=assoc.get("association_score"),
                        source_database="OpenTargets",
                        evidence_type="disease_association",
                        is_directed=True,
                        extra_metadata={"datatype_scores": assoc.get("evidence_scores", {})},
                    ))
                    inserted += 1

            await self.db.commit()
            await self._finish_job(job, len(associations), inserted)
            await self.update_datasource_status("opentargets", "success", records=len(associations))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("opentargets", "failed", errors=1)
            raise

    # ── STRING ─────────────────────────────────────────────────────────────
    async def ingest_string(self, job_id: int, gene_symbols: List[str], min_score: int = 700):
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with StringClient() as client:
                data = await client.get_interaction_partners(gene_symbols, required_score=min_score)

            inserted = 0
            for item in data:
                sym_a = item.get("preferredName_A")
                sym_b = item.get("preferredName_B")
                if not sym_a or not sym_b:
                    continue

                res_a = await self.db.execute(select(Gene).where(Gene.symbol == sym_a))
                gene_a = res_a.scalar_one_or_none()
                if not gene_a:
                    gene_a = Gene(symbol=sym_a)
                    self.db.add(gene_a)
                    await self.db.flush()

                res_b = await self.db.execute(select(Gene).where(Gene.symbol == sym_b))
                gene_b = res_b.scalar_one_or_none()
                if not gene_b:
                    gene_b = Gene(symbol=sym_b)
                    self.db.add(gene_b)
                    await self.db.flush()

                score = float(item.get("score", 0))
                self.db.add(Interaction(
                    interaction_type="PPI",
                    source_gene_id=gene_a.id,
                    target_gene_id=gene_b.id,
                    confidence_score=score,
                    evidence_score=score,
                    source_database="STRING",
                    evidence_type="protein_protein_interaction",
                    is_directed=False,
                    extra_metadata={"nscore": item.get("nscore"), "fscore": item.get("fscore")},
                ))
                inserted += 1

            await self.db.commit()
            await self._finish_job(job, len(data), inserted)
            await self.update_datasource_status("string", "success", records=len(data))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("string", "failed", errors=1)
            raise

    # ── DGIdb ──────────────────────────────────────────────────────────────
    async def ingest_dgidb(self, job_id: int, genes: List[str]):
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with DGIdbClient() as client:
                interactions = await client.get_interactions(genes=genes)

            inserted = 0
            for inter in interactions:
                drug_name = inter.get("drug_name")
                gene_symbol = inter.get("gene_symbol")
                if not drug_name or not gene_symbol:
                    continue

                res_d = await self.db.execute(select(Drug).where(Drug.name == drug_name))
                drug = res_d.scalars().first()
                if not drug:
                    drug = Drug(name=drug_name, approval_status="unknown")
                    self.db.add(drug)
                    await self.db.flush()

                res_g = await self.db.execute(select(Gene).where(Gene.symbol == gene_symbol))
                gene = res_g.scalars().first()
                if not gene:
                    gene = Gene(symbol=gene_symbol)
                    self.db.add(gene)
                    await self.db.flush()

                self.db.add(Interaction(
                    interaction_type="DrugTarget",
                    source_gene_id=gene.id,
                    drug_id=drug.id,
                    source_database="DGIdb",
                    evidence_type=inter.get("interaction_type", "unknown"),
                    is_directed=True,
                    extra_metadata={"pmids": inter.get("pmids", []), "source": inter.get("source")},
                ))
                inserted += 1

            await self.db.commit()
            await self._finish_job(job, len(interactions), inserted)
            await self.update_datasource_status("dgidb", "success", records=len(interactions))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("dgidb", "failed", errors=1)
            raise

    # ── ChEMBL ─────────────────────────────────────────────────────────────
    async def ingest_chembl(self, job_id: int, chembl_ids: List[str]):
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            inserted = 0
            async with ChEMBLClient() as client:
                for chembl_id in chembl_ids:
                    mol = await client.get_molecule(chembl_id)
                    if not mol:
                        continue
                    pref_name = mol.get("pref_name") or chembl_id
                    res = await self.db.execute(select(Drug).where(Drug.chembl_id == chembl_id))
                    drug = res.scalar_one_or_none()
                    if not drug:
                        drug = Drug(
                            name=pref_name,
                            chembl_id=chembl_id,
                            max_phase=int(float(mol.get("max_phase") or 0)),
                            approval_status="approved" if int(float(mol.get("max_phase") or 0)) >= 4 else "investigational",
                            molecular_formula=mol.get("molecule_properties", {}).get("full_molformula"),
                            molecular_weight=float(mwt) if (mwt := mol.get("molecule_properties", {}).get("full_mwt")) else None,
                        )
                        self.db.add(drug)
                        inserted += 1
                    else:
                        drug.max_phase = int(float(mol.get("max_phase") or drug.max_phase or 0))
                        drug.name = pref_name

            await self.db.commit()
            await self._finish_job(job, len(chembl_ids), inserted)
            await self.update_datasource_status("chembl", "success", records=len(chembl_ids))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("chembl", "failed", errors=1)
            raise

    # ── UniProt ────────────────────────────────────────────────────────────
    async def ingest_uniprot(self, job_id: int, query: str, size: int = 50):
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with UniProtClient() as client:
                raw = await client.search_proteins(query, size=size)

            # UniProt returns {"results": [...], "facets": [...]}
            proteins = raw.get("results", []) if isinstance(raw, dict) else raw
            inserted = 0
            for prot in proteins:
                if not isinstance(prot, dict):
                    continue
                genes = prot.get("genes", [])
                symbol = genes[0].get("geneName", {}).get("value") if genes else None
                if not symbol:
                    continue
                res = await self.db.execute(select(Gene).where(Gene.symbol == symbol))
                gene = res.scalar_one_or_none()
                if not gene:
                    gene = Gene(
                        symbol=symbol,
                        name=prot.get("proteinDescription", {})
                              .get("recommendedName", {})
                              .get("fullName", {}).get("value"),
                    )
                    self.db.add(gene)
                    await self.db.flush()
                uniprot_acc = prot.get("primaryAccession")
                if uniprot_acc:
                    res2 = await self.db.execute(
                        select(Protein).where(Protein.uniprot_id == uniprot_acc)
                    )
                    if not res2.scalar_one_or_none():
                        protein = Protein(
                            uniprot_id=uniprot_acc,
                            gene_id=gene.id,
                            sequence=prot.get("sequence", {}).get("value"),
                        )
                        self.db.add(protein)
                        inserted += 1
            await self.db.commit()
            await self._finish_job(job, len(proteins), inserted)
            await self.update_datasource_status("uniprot", "success", records=len(proteins))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("uniprot", "failed", errors=1)
            raise

    # ── ClinicalTrials ─────────────────────────────────────────────────────
    async def ingest_clinicaltrials(self, job_id: int, condition: str, intervention: str = None):
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with ClinicalTrialsClient() as client:
                raw = await client.search_trials(condition, intervention=intervention)

            # ClinicalTrials v2 returns {"studies": [...], "nextPageToken": ..., "totalCount": N}
            trials = raw.get("studies", []) if isinstance(raw, dict) else raw

            # Resolve disease row once (case-insensitive name match)
            res = await self.db.execute(
                select(Disease).where(Disease.name.ilike(f"%{condition}%"))
            )
            disease = res.scalars().first()
            if not disease:
                logger.warning(
                    f"[ClinicalTrials] no Disease row matching '{condition}' — nothing to link"
                )
                await self._finish_job(job, len(trials), 0)
                await self.update_datasource_status("clinicaltrials", "success", records=len(trials))
                return

            inserted = 0
            for trial in trials:
                if not isinstance(trial, dict):
                    continue

                nct_id = (
                    trial.get("protocolSection", {})
                         .get("identificationModule", {})
                         .get("nctId")
                )
                if not nct_id:
                    continue

                # ── Extract drug/intervention name ─────────────────────────
                # Previous version stored only disease_id → _resolve_source in
                # builder.py returned None → edge was silently dropped → 0 edges.
                # Fix: parse the first DRUG-typed intervention so we can create a
                # Drug node and link it drug_id → disease_id (a resolvable edge).
                drug_name: str | None = None
                arms = (
                    trial.get("protocolSection", {})
                         .get("armsInterventionsModule", {})
                         .get("interventions", []) or []
                )
                # Only accept DRUG or BIOLOGICAL interventions — never BEHAVIORAL,
                # PROCEDURE, DEVICE, DIETARY_SUPPLEMENT, OTHER, etc.
                # Dropping the old fallback that accepted any intervention type
                # is what was causing "Questionnaire", "fecal microbiome", etc.
                # to appear as Drug rows in the database.
                _CHEMICAL_TYPES = {"DRUG", "BIOLOGICAL"}
                for arm in arms:
                    if isinstance(arm, dict) and arm.get("type", "").upper() in _CHEMICAL_TYPES:
                        drug_name = arm.get("name")
                        if drug_name:
                            break
                # NO fallback — if no DRUG/BIOLOGICAL found, skip this trial entirely

                if not drug_name:
                    # No usable drug in this trial → skip (no edge possible)
                    continue

                # Upsert Drug row
                res_d = await self.db.execute(select(Drug).where(Drug.name == drug_name))
                drug = res_d.scalars().first()
                if not drug:
                    drug = Drug(name=drug_name, approval_status="investigational")
                    self.db.add(drug)
                    await self.db.flush()

                # Create DrugDisease interaction with both drug_id AND disease_id set
                # so the builder can resolve source=Drug, target=Disease → real graph edge
                self.db.add(Interaction(
                    interaction_type="ClinicalTrial",
                    drug_id=drug.id,
                    disease_id=disease.id,
                    source_database="ClinicalTrials",
                    evidence_type="clinical_trial",
                    is_directed=True,
                    extra_metadata={
                        "nct_id": nct_id,
                        "phase": trial.get("phase"),
                        "status": trial.get("overallStatus"),
                        "title": trial.get("briefTitle"),
                    },
                ))
                inserted += 1

            await self.db.commit()
            await self._finish_job(job, len(trials), inserted)
            await self.update_datasource_status("clinicaltrials", "success", records=len(trials))
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("clinicaltrials", "failed", errors=1)
            raise

    # ── GDC (TCGA) ─────────────────────────────────────────────────────────
    async def ingest_gdc(self, job_id: int, project: str, gene_ids: List[str] = None,
                          min_co_occurrences: int = 2):
        """
        Ingest somatic mutation records from GDC, upsert Gene nodes for
        every mutated gene (existing behavior), AND derive Edge type 4 —
        Co-mutation edges from co-occurrence of mutations within the same
        patient case (new).

        FIX C10 / Edge type 4: this previously only created Gene nodes and
        discarded the rest of each mutation record, so no Gene-Gene edges
        were ever derived from somatic mutation data even though the client
        fetched it. GDCClient.query_ssms now also requests
        occurrence.case.case_id, which lets us group mutations by patient
        and count how often each gene pair is mutated together in the same
        case. Pairs co-occurring in fewer than min_co_occurrences distinct
        cases are dropped as noise rather than stored as an edge.
        """
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            async with GDCClient() as client:
                raw = await client.query_ssms(project=project, gene_ids=gene_ids)

            # GDC returns {"data": {"hits": [...], "pagination": {...}}, "warnings": {}}
            hits = raw.get("data", {}).get("hits", []) if isinstance(raw, dict) else []

            genes_seen = set()
            case_genes: Dict[str, set] = defaultdict(set)
            inserted_genes = 0

            for mut in hits:
                if not isinstance(mut, dict):
                    continue
                # Try direct gene_id field first, then nested consequence path
                gene_symbol = mut.get("gene_id")
                if not gene_symbol:
                    consequences = mut.get("consequence", [])
                    if consequences and isinstance(consequences, list):
                        first = consequences[0]
                        if isinstance(first, dict):
                            gene_symbol = (
                                first.get("transcript", {})
                                     .get("gene", {})
                                     .get("symbol")
                            )
                if not gene_symbol:
                    continue

                if gene_symbol not in genes_seen:
                    genes_seen.add(gene_symbol)
                    res = await self.db.execute(select(Gene).where(Gene.symbol == gene_symbol))
                    gene = res.scalar_one_or_none()
                    if not gene:
                        gene = Gene(symbol=gene_symbol, is_oncogene=True)
                        self.db.add(gene)
                        await self.db.flush()
                        inserted_genes += 1

                # Record which patient case(s) carried this mutation, so we
                # can derive co-occurrence edges below. A single ssm can
                # have multiple occurrences (multiple cases with the same
                # mutation).
                for occ in (mut.get("occurrence") or []):
                    case = occ.get("case", {}) if isinstance(occ, dict) else {}
                    case_id = case.get("case_id")
                    if case_id:
                        case_genes[case_id].add(gene_symbol)

            # ── Edge type 4: Co-mutation ─────────────────────────────────
            # For every case with 2+ distinct mutated genes, count every
            # unordered gene pair as one co-occurrence across the cohort.
            pair_counts: Counter = Counter()
            for genes_in_case in case_genes.values():
                if len(genes_in_case) < 2:
                    continue
                for sym_a, sym_b in combinations(sorted(genes_in_case), 2):
                    pair_counts[(sym_a, sym_b)] += 1

            total_cases = len(case_genes)
            inserted_edges = 0
            for (sym_a, sym_b), co_count in pair_counts.items():
                if co_count < min_co_occurrences:
                    continue

                res_a = await self.db.execute(select(Gene).where(Gene.symbol == sym_a))
                gene_a = res_a.scalar_one_or_none()
                res_b = await self.db.execute(select(Gene).where(Gene.symbol == sym_b))
                gene_b = res_b.scalar_one_or_none()
                if not gene_a or not gene_b:
                    continue

                # Dedup manually: drug_id/disease_id are NULL for these
                # edges, and NULL != NULL in the table's unique constraint,
                # so re-running this job would otherwise silently duplicate
                # every pair instead of being caught by the DB.
                existing = await self.db.execute(
                    select(Interaction).where(
                        Interaction.interaction_type == "CoMutation",
                        Interaction.source_gene_id == gene_a.id,
                        Interaction.target_gene_id == gene_b.id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                frequency = (co_count / total_cases) if total_cases else 0.0
                self.db.add(Interaction(
                    interaction_type="CoMutation",
                    source_gene_id=gene_a.id,
                    target_gene_id=gene_b.id,
                    confidence_score=frequency,
                    evidence_score=float(co_count),
                    source_database="GDC",
                    evidence_type="somatic_co_mutation",
                    is_directed=False,
                    extra_metadata={
                        "project": project,
                        "co_occurrence_count": co_count,
                        "total_cases_with_mutations": total_cases,
                    },
                ))
                inserted_edges += 1

            await self.db.commit()
            await self._finish_job(job, len(hits), inserted_genes + inserted_edges)
            await self.update_datasource_status("gdc", "success", records=len(hits))
            logger.info(
                f"[GDC] {project}: {inserted_genes} new genes, "
                f"{inserted_edges} new CoMutation edges "
                f"(from {total_cases} cases, {len(pair_counts)} candidate pairs, "
                f"min_co_occurrences={min_co_occurrences})"
            )
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("gdc", "failed", errors=1)
            raise

    # ── cBioPortal (Edge type 4 fallback for diseases with no GDC project) ──
    async def ingest_cbioportal(self, job_id: int, study_id: str, gene_symbols: List[str] = None,
                                 min_co_occurrences: int = 2):
        """
        Derive Edge type 4 — Co-mutation edges from a public cBioPortal
        study, for diseases with no dedicated public GDC/TARGET project
        (e.g. Ewing Sarcoma, Medulloblastoma). Same co-occurrence logic as
        ingest_gdc: group mutations by patient, count gene pairs mutated
        together in the same patient, keep pairs meeting min_co_occurrences.

        study_id must be resolved first via CBioPortalClient.search_studies()
        — do not guess this string, cBioPortal study IDs are per-publication
        and multiple cohorts may exist for the same disease.
        """
        job = await self._load_job(job_id)
        if not job:
            return
        await self._start_job(job)
        try:
            if not gene_symbols:
                raise ValueError(
                    "ingest_cbioportal requires gene_symbols — see FIX C13 "
                    "in cbioportal.py."
                )
            async with CBioPortalClient() as client:
                mutations = await client.get_mutations(study_id, gene_symbols)
                try:
                    structural_variants = await client.get_structural_variants(study_id, gene_symbols)
                except ValueError as sv_err:
                    logger.info(f"[cBioPortal] {study_id}: {sv_err}")
                    structural_variants = []

            genes_seen = set()
            patient_genes: Dict[str, set] = defaultdict(set)
            inserted_genes = 0

            for mut in mutations:
                if not isinstance(mut, dict):
                    continue
                gene_symbol = (mut.get("gene") or {}).get("hugoGeneSymbol")
                patient_id = mut.get("patientId") or mut.get("sampleId")
                if not gene_symbol or not patient_id:
                    continue

                if gene_symbol not in genes_seen:
                    genes_seen.add(gene_symbol)
                    res = await self.db.execute(select(Gene).where(Gene.symbol == gene_symbol))
                    gene = res.scalar_one_or_none()
                    if not gene:
                        gene = Gene(symbol=gene_symbol, is_oncogene=True)
                        self.db.add(gene)
                        await self.db.flush()
                        inserted_genes += 1

                patient_genes[patient_id].add(gene_symbol)

            # Merge in structural variants (fusions) — same co-occurrence
            # logic, but each SV record names TWO genes directly (site1Gene,
            # site2Gene) rather than one gene per record like a mutation.
            for sv in structural_variants:
                if not isinstance(sv, dict):
                    continue
                patient_id = sv.get("patientId") or sv.get("sampleId")
                if not patient_id:
                    continue
                # FIX C15: the actual API response has flat site1HugoSymbol /
                # site2HugoSymbol fields, not a nested site1Gene.hugoGeneSymbol
                # structure — confirmed against a real response (see
                # es_dfarber_broad_2014 sample dump: 'site1HugoSymbol': 'EWSR1',
                # 'site2HugoSymbol': 'ERG'). The old field names silently
                # matched nothing on every real record.
                for symbol_field in ("site1HugoSymbol", "site2HugoSymbol"):
                    gene_symbol = sv.get(symbol_field)
                    if not gene_symbol:
                        continue
                    if gene_symbol not in genes_seen:
                        genes_seen.add(gene_symbol)
                        res = await self.db.execute(select(Gene).where(Gene.symbol == gene_symbol))
                        gene = res.scalar_one_or_none()
                        if not gene:
                            gene = Gene(symbol=gene_symbol, is_oncogene=True)
                            self.db.add(gene)
                            await self.db.flush()
                            inserted_genes += 1
                    patient_genes[patient_id].add(gene_symbol)

            pair_counts: Counter = Counter()
            for genes_in_patient in patient_genes.values():
                if len(genes_in_patient) < 2:
                    continue
                for sym_a, sym_b in combinations(sorted(genes_in_patient), 2):
                    pair_counts[(sym_a, sym_b)] += 1

            total_patients = len(patient_genes)
            inserted_edges = 0
            for (sym_a, sym_b), co_count in pair_counts.items():
                if co_count < min_co_occurrences:
                    continue

                res_a = await self.db.execute(select(Gene).where(Gene.symbol == sym_a))
                gene_a = res_a.scalar_one_or_none()
                res_b = await self.db.execute(select(Gene).where(Gene.symbol == sym_b))
                gene_b = res_b.scalar_one_or_none()
                if not gene_a or not gene_b:
                    continue

                existing = await self.db.execute(
                    select(Interaction).where(
                        Interaction.interaction_type == "CoMutation",
                        Interaction.source_gene_id == gene_a.id,
                        Interaction.target_gene_id == gene_b.id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                frequency = (co_count / total_patients) if total_patients else 0.0
                self.db.add(Interaction(
                    interaction_type="CoMutation",
                    source_gene_id=gene_a.id,
                    target_gene_id=gene_b.id,
                    confidence_score=frequency,
                    evidence_score=float(co_count),
                    source_database="cBioPortal",
                    evidence_type="somatic_co_mutation",
                    is_directed=False,
                    extra_metadata={
                        "study_id": study_id,
                        "co_occurrence_count": co_count,
                        "total_patients": total_patients,
                    },
                ))
                inserted_edges += 1

            await self.db.commit()
            total_records = len(mutations) + len(structural_variants)
            await self._finish_job(job, total_records, inserted_genes + inserted_edges)
            await self.update_datasource_status("cbioportal", "success", records=total_records)
            logger.info(
                f"[cBioPortal] {study_id}: {inserted_genes} new genes, "
                f"{inserted_edges} new CoMutation edges "
                f"({len(mutations)} mutation records, {len(structural_variants)} "
                f"structural variant records, from {total_patients} patients, "
                f"{len(pair_counts)} candidate pairs, min_co_occurrences={min_co_occurrences})"
            )
        except Exception as exc:
            await self._fail_job(job, exc)
            await self.update_datasource_status("cbioportal", "failed", errors=1)
            raise