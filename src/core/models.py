import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CatalogItem:
    raw_sku: str
    manufacturer: str
    product_group: str
    row_number: int = 0


@dataclass(frozen=True)
class ValidationResult:
    raw_sku: str
    search_key: str
    manufacturer: str
    product_group: str
    is_valid: bool
    matched_mask: str | None = None
    reason: str = ""
    row_number: int = 0


@dataclass
class CertificateRuleSet:
    manufacturer: str
    product_group: str
    mask_length: int
    prefix_length: int
    suffix_pattern: str
    allowed_prefixes: list[str]
    compiled_regex: re.Pattern = field(init=False)
    prefix_set: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.prefix_set = set(self.allowed_prefixes)
        joined_prefixes = "|".join(re.escape(p) for p in self.allowed_prefixes)
        pattern = f"^(?:{joined_prefixes}){self.suffix_pattern}$"
        # Полное сопоставление строки без многострочного режима
        self.compiled_regex = re.compile(pattern)
        logger.info(
            "Скомпилированы правила для '%s' (%s): %d префиксов, шаблон %s",
            self.manufacturer,
            self.product_group,
            len(self.allowed_prefixes),
            pattern,
        )

    @classmethod
    def from_yaml(cls, config_path: Path) -> "CertificateRuleSet":
        logger.info("Загрузка правил сертификата из файла: %s", config_path)
        if not config_path.exists():
            logger.error("Файл не найден: %s", config_path)
            raise FileNotFoundError(f"Файл не найден: {config_path}")

        with config_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        return cls(
            manufacturer=str(data["manufacturer"]),
            product_group=str(data["product_group"]),
            mask_length=int(data.get("mask_length", 7)),
            prefix_length=int(data.get("prefix_length", 3)),
            suffix_pattern=str(data.get("suffix_pattern", "[A-Z0-9]{4}")),
            allowed_prefixes=list(data["allowed_prefixes"]),
        )
