##############################################################################
# app/streamlit_app/api_client.py
#
# HTTP client for FastAPI backend (Clinexus agents).
##############################################################################

import requests
import logging
from typing import Dict, Any, Optional
from config import API_BASE_URL

logger = logging.getLogger(__name__)

class ClinexusAPIClient:
    """Client for Clinexus FastAPI backend."""

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30

    def analyze(
        self,
        nct_id: str,
        researcher_id: str,
    ) -> Dict[str, Any]:
        """
        Trigger analysis for a clinical trial.
        
        Args:
            nct_id: Clinical trial NCT ID
            researcher_id: ID of researcher triggering analysis
            
        Returns:
            Response with analysis_id and status
        """
        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/analyze",
                json={
                    "nct_id": nct_id,
                    "researcher_id": researcher_id,
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to trigger analysis: {e}")
            raise

    def get_analysis_status(
        self,
        analysis_id: str,
    ) -> Dict[str, Any]:
        """Get status of an ongoing analysis."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/analyses/{analysis_id}",
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch analysis status: {e}")
            raise

    def get_study_details(
        self,
        nct_id: str,
    ) -> Dict[str, Any]:
        """Fetch study details from ClinicalTrials.gov."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/studies/{nct_id}",
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch study details: {e}")
            raise

    def health_check(self) -> bool:
        """Check if backend is healthy."""
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=5,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Backend health check failed: {e}")
            return False


# Global client instance
_client = None

def get_client() -> ClinexusAPIClient:
    """Get or create global API client."""
    global _client
    if _client is None:
        _client = ClinexusAPIClient()
    return _client
