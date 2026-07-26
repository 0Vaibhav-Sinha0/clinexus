##############################################################################
# ingestion/document_parser.py
#
# Converts raw API data into clean ParsedStudy and ParsedPaper objects.
# Serves as a boundary checkpoint: messy data from APIs becomes typed,
# predictable data for the rest of the Clinexus system.
# Consumed by run_ingestion.py; not intended to be run directly.
##############################################################################


from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from config.logging_config import setup_logging

logger = setup_logging(__name__)


# ─────────────────────────────────────────────────────────────
# INTERNAL DATA SHAPES (SCHEMAS)
# ─────────────────────────────────────────────────────────────

class ParsedStudy(BaseModel):
    """
    A clinical trial study, cleaned and structured.
    This is the canonical form for studies throughout Clinexus.
    """

    nct_id: str
    title: str
    sponsor: str
    phase: str
    status: str
    conditions: list[str]
    interventions: list[str]
    primary_outcome: str
    secondary_outcomes: list[str]
    start_date: str
    completion_date: str
    results_posted: bool
    enrollment: int
    protocol_amendments: list[dict[str, Any]]
    raw_data: dict[str, Any]
    parsed_at: str


class ParsedPaper(BaseModel):
    """
    A PubMed research paper, cleaned and structured.
    Canonical form for papers throughout Clinexus.
    """

    pmid: str
    title: str
    abstract: str
    journal: str
    pub_date: str
    authors: list[str]
    nct_ids_referenced: list[str]
    source: str = "pubmed"
    word_count: int
    parsed_at: str


# ─────────────────────────────────────────────────────────────
# THE PARSER CLASS
# ─────────────────────────────────────────────────────────────

class DocumentParser:
    """
    Converts raw API data into clean ParsedStudy and ParsedPaper objects.

    Usage:
        parser = DocumentParser()
        study = parser.parse_study(raw_study_dict)
        paper = parser.parse_paper(raw_paper_dict)
    """

    def parse_study(self, raw: dict[str, Any]) -> ParsedStudy | None:
        """
        Cleans one raw ClinicalTrials.gov study record, extracting only
        the fields we need from its deeply nested structure.

        Returns:
            ParsedStudy if successful, None if essential fields are missing.
        """

        try:
            protocol_section = raw.get("protocolSection", {})
            id_module        = protocol_section.get("identificationModule", {})
            status_module    = protocol_section.get("statusModule", {})
            design_module    = protocol_section.get("designModule", {})
            outcomes_module  = protocol_section.get("outcomesModule", {})

            nct_id  = id_module.get("nctId", "")
            title   = id_module.get("briefTitle", "")
            sponsor = id_module.get("organization", {}).get("name", "")

            if not nct_id or not title:
                logger.warning(
                    f"Study missing required fields | "
                    f"nct_id={nct_id} | title={title}"
                )
                return None

            phase = design_module.get("phases", ["NA"])[0] if design_module.get(
                "phases"
            ) else "NA"

            status = status_module.get("overallStatus", "")
            has_results = status_module.get("resultsFirstSubmitDate") is not None

            conditions = [
                c.get("name", "")
                for c in id_module.get("conditions", [])
                if c.get("name")
            ]

            interventions = [
                i.get("name", "")
                for i in design_module.get("interventions", [])
                if i.get("name")
            ]

            primary_outcome = ""
            if outcomes_module.get("primaryOutcomes"):
                primary_outcome = outcomes_module["primaryOutcomes"][0].get(
                    "measure", ""
                )

            secondary_outcomes = [
                o.get("measure", "")
                for o in outcomes_module.get("secondaryOutcomes", [])
                if o.get("measure")
            ]

            start_date = (
                status_module.get("startDateStruct", {}).get("date", "")
            )

            completion_date = (
                status_module.get("primaryCompletionDateStruct", {}).get("date", "")
                or status_module.get("completionDateStruct", {}).get("date", "")
            )

            enrollment_info = design_module.get("enrollmentInfo", {})
            enrollment = enrollment_info.get("count", 0)
            try:
                enrollment = int(enrollment)
            except (ValueError, TypeError):
                enrollment = 0

            annotations      = raw.get("annotationSection", {})
            amendment_module = annotations.get("annotationModule", {})
            amendments       = amendment_module.get("unpostedAnnotation", {})

            protocol_amendments = []
            if amendments:
                protocol_amendments = [
                    {
                        "date":        amendments.get("unpostedResponsibleParty", ""),
                        "description": str(amendments),
                    }
                ]

            return ParsedStudy(
                nct_id=nct_id,
                title=title,
                sponsor=sponsor,
                phase=phase,
                status=status,
                conditions=conditions,
                interventions=interventions,
                primary_outcome=primary_outcome,
                secondary_outcomes=secondary_outcomes,
                start_date=start_date,
                completion_date=completion_date,
                results_posted=has_results,
                enrollment=enrollment,
                protocol_amendments=protocol_amendments,
                raw_data=raw,
                parsed_at=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            nct_id = raw.get("protocolSection", {}).get(
                "identificationModule", {}
            ).get("nctId", "UNKNOWN")
            logger.error(
                f"Failed to parse study | nct_id={nct_id} | error={e}"
            )
            return None

    def parse_studies(
        self,
        raw_studies: list[dict[str, Any]],
    ) -> list[ParsedStudy]:
        """
        Parses multiple raw studies. Failed studies are skipped, not fatal.

        Args:
            raw_studies: List of raw study dicts from the API.

        Returns:
            List of successfully parsed ParsedStudy objects.
        """

        parsed = []
        failed = 0

        for raw in raw_studies:
            study = self.parse_study(raw)
            if study:
                parsed.append(study)
            else:
                failed += 1

        logger.info(
            f"Parsed studies | "
            f"success={len(parsed)} | "
            f"failed={failed} | "
            f"total={len(raw_studies)}"
        )

        return parsed

    def parse_paper(self, raw: dict[str, Any]) -> ParsedPaper | None:
        """
        Cleans one raw PubMed paper record and builds the typed object.

        Args:
            raw: One raw paper dictionary from pubmed_client.py.

        Returns:
            ParsedPaper if successful, None if something failed.
        """

        try:
            abstract = raw.get("abstract", "")
            word_count = len(abstract.split()) if abstract else 0

            return ParsedPaper(
                pmid=raw.get("pmid", ""),
                title=raw.get("title", ""),
                abstract=abstract,
                journal=raw.get("journal", ""),
                pub_date=raw.get("pub_date", ""),
                authors=raw.get("authors", []),
                nct_ids_referenced=raw.get("nct_ids_referenced", []),
                source="pubmed",
                word_count=word_count,
                parsed_at=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            logger.error(
                f"Failed to parse paper | "
                f"pmid={raw.get('pmid', 'UNKNOWN')} | "
                f"error={e}"
            )
            return None

    def parse_papers(
        self,
        raw_papers: list[dict[str, Any]],
    ) -> list[ParsedPaper]:
        """
        Parses multiple raw papers. Same pattern as parse_studies.

        Args:
            raw_papers: List of raw paper dicts from pubmed_client.py.

        Returns:
            List of successfully parsed ParsedPaper objects.
        """

        parsed = []
        failed = 0

        for raw in raw_papers:
            paper = self.parse_paper(raw)
            if paper:
                parsed.append(paper)
            else:
                failed += 1

        logger.info(
            f"Parsed papers | "
            f"success={len(parsed)} | "
            f"failed={failed} | "
            f"total={len(raw_papers)}"
        )

        return parsed