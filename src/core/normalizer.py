from abc import ABC, abstractmethod
import string
from src.core.logger import get_logger

logger = get_logger(__name__)

_LATIN_UPPER_TABLE = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)
_NON_BREAKING_SPACES = ("\u00a0", "\u202f", "\u2007")


class BaseNormalizer(ABC):
    """Абстракция нормализатора поискового ключа (принцип DIP/OCP)."""

    @abstractmethod
    def normalize_sku(self, raw_sku: str) -> str:
        """Формирует поисковый ключ из исходного артикула."""

    @abstractmethod
    def normalize_text_field(self, value: str) -> str:
        """Нормализует текстовое поле (производитель, товарная группа) для сравнения."""


class SkuNormalizer(BaseNormalizer):
    def normalize_sku(self, raw_sku: str) -> str:
        cleaned = raw_sku
        for nbsp in _NON_BREAKING_SPACES:
            cleaned = cleaned.replace(nbsp, " ")
        cleaned = cleaned.strip(" ")
        search_key = cleaned.translate(_LATIN_UPPER_TABLE)

        logger.debug("Нормализация SKU: raw=%r -> search_key=%r", raw_sku, search_key)
        return search_key

    def normalize_text_field(self, value: str) -> str:
        cleaned = value
        for nbsp in _NON_BREAKING_SPACES:
            cleaned = cleaned.replace(nbsp, " ")
        return " ".join(cleaned.strip().split()).upper()
