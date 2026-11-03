import pytest

from pathlib import Path
from src.core.models import CatalogItem, CertificateRuleSet
from src.core.normalizer import SkuNormalizer
from src.core.service import CertificateVerificationService
from src.core.validator import MaskValidator
from src.reports.excel_report import ExcelReportExporter, TabularCatalogReader

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "masks_hilex.yaml"


@pytest.fixture()
def validator() -> MaskValidator:
    rules = CertificateRuleSet.from_yaml(CONFIG_PATH)
    normalizer = SkuNormalizer()
    return MaskValidator(rules=rules, normalizer=normalizer)


@pytest.mark.parametrize(
    ("raw_sku", "expected_mask"),
    [
        ("4VB0000", "4VB****"),
        ("9BBA1Z9", "9BB****"),
        ("  4vb0000  ", "4VB****"),
        ("\u00a09tb12o0\u00a0", "9TB****"),
        ("1PB9999", "1PB****"),
        ("7HBZ0A1", "7HB****"),
    ],
)
def test_valid_skus_match_masks(
    validator: MaskValidator,
    raw_sku: str,
    expected_mask: str,
) -> None:
    item = CatalogItem(
        raw_sku=raw_sku,
        manufacturer="HI-LEX CORPORATION",
        product_group="тросы стояночного тормоза",
        row_number=1,
    )
    result = validator.validate(item)

    assert result.is_valid is True
    assert result.raw_sku == raw_sku
    assert result.matched_mask == expected_mask


@pytest.mark.parametrize(
    ("raw_sku", "expected_reason_substring"),
    [
        ("4VB123", "Неверная длина"),
        ("4VB12345", "Неверная длина"),
        ("4VB12-3", "Дефис внутри артикула"),
        ("4QB1234", "Префикс 4QB отсутствует в перечне"),
        ("4VB12А3", "Буква А в строке кириллическая"),  # Кириллическая А
        ("4VB12.3", "Точка внутри артикула"),
        ("4VB 123", "Пробел внутри артикула"),
        ("4VB123\n", "перевод строки"),
    ],
)
def test_control_exceptions_from_spec(
    validator: MaskValidator,
    raw_sku: str,
    expected_reason_substring: str,
) -> None:
    item = CatalogItem(
        raw_sku=raw_sku,
        manufacturer="HI-LEX CORPORATION",
        product_group="тросы стояночного тормоза",
        row_number=2,
    )
    result = validator.validate(item)

    assert result.is_valid is False
    assert result.matched_mask is None
    assert expected_reason_substring in result.reason


def test_wrong_manufacturer_or_product_group_rejected(validator: MaskValidator) -> None:
    wrong_mfg = CatalogItem(
        raw_sku="4VB0000",
        manufacturer="OTHER CORP",
        product_group="тросы стояночного тормоза",
    )
    wrong_group = CatalogItem(
        raw_sku="4VB0000",
        manufacturer="HI-LEX CORPORATION",
        product_group="тормозные колодки",
    )

    res_mfg = validator.validate(wrong_mfg)
    res_group = validator.validate(wrong_group)

    assert res_mfg.is_valid is False
    assert "Несоответствие производителя" in res_mfg.reason
    assert res_group.is_valid is False
    assert "Несоответствие товарной группы" in res_group.reason


def test_end_to_end_excel_processing(tmp_path: Path) -> None:
    rules = CertificateRuleSet.from_yaml(CONFIG_PATH)
    service = CertificateVerificationService(
        validator=MaskValidator(rules=rules, normalizer=SkuNormalizer()),
        reader=TabularCatalogReader(),
        exporter=ExcelReportExporter(),
    )

    sample_file = CONFIG_PATH.parent.parent / "data" / "sample_catalog.xlsx"
    output_file = tmp_path / "report.xlsx"

    summary = service.process_file(sample_file, output_file)
    assert output_file.exists()
    assert summary.total_processed == len(summary.valid_items) + len(
        summary.excluded_items
    )
    assert len(summary.valid_items) >= 2
    assert len(summary.excluded_items) >= 5
