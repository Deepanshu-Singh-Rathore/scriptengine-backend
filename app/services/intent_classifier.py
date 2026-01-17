"""
Rule-based intent classification.
"""
from typing import Dict, List


class IntentClassifier:
    """Rule-based intent classifier."""
    
    # Intent patterns
    INTENT_PATTERNS = {
        "etl": [
            "remove quotes", "strip quotes", "remove quotes from csv",
            "strip quotes from csv", "process csv files from gcs",
            "process xlsx files from gcs", "process zip files from gcs",
            "gcs file processing", "archive and process", "etl pipeline",
            "multi-format etl", "gcs etl", "google cloud storage"
        ],
        "conversion": [
            "normalize", "transform", "clean", "process",
            "data transformation", "data cleaning"
        ],
        "format_conversion": [
            "convert csv to xlsx", "convert xlsx to csv",
            "csv to excel", "excel to csv", "format conversion"
        ],
        "api_to_bq": [
            "api to bigquery", "load api to bigquery",
            "api to bq", "fetch api to bigquery"
        ],
        "sac_api_to_bq": [
            "sac api to bigquery", "sac to bigquery",
            "sac api to bq", "sac analytics to bigquery"
        ],
        "gcs_to_bq": [
            "gcs to bigquery", "gcs to bq",
            "google cloud storage to bigquery", "storage to bigquery"
        ],
        "validation": [
            "validate", "validation", "data quality",
            "check data", "verify data"
        ]
    }
    
    @classmethod
    def classify(cls, user_input: str) -> str:
        """Classify user intent from input."""
        input_lower = user_input.lower()
        
        # Check each intent pattern
        for intent, patterns in cls.INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in input_lower:
                    return intent
        
        # Default to conversion if no match
        return "conversion"
    
    @classmethod
    def get_llm_enabled_types(cls) -> List[str]:
        """Get script types that support LLM generation."""
        return ["conversion", "format_conversion", "etl"]
