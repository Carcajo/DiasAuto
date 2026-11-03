from dataclasses import dataclass
from pathlib import Path

from src.core.logger import get_logger
from src.core.models import CatalogItem, ValidationResult
from src.core.validator import BaseValidator
from src.reports.excel_report import BaseCatalogReader, BaseReportExporter

logger = get_logger(__name__)


@dataclass(frozen=True)
class BatchVerificationSummary:
    """Сводный результат пакетной проверки каталога."""

    total_processed: int
    valid_items: list[ValidationResult]
    excluded_items: list[ValidationResult]
    report_path: Path | None = None


class CertificateVerificationService:
    """
    Прикладной сервис для пакетной проверки каталога по масочному сертификату.
    Соблюдает принцип инверсии зависимостей (DIP): зависит от абстракций валидатора,
    ридера и экспортера.
    """

    def __init__(
        self,
        validator: BaseValidator,
        reader: BaseCatalogReader,
        exporter: BaseReportExporter,
    ) -> None:
        self._validator = validator
        self._reader = reader
        self._exporter = exporter

    def verify_items(self, items: list[CatalogItem]) -> BatchVerificationSummary:
        """Проверяет список позиций в памяти и разделяет их на принятые и исключения."""
        logger.info("Старт проверки пакета из %d позиций", len(items))
        valid_items = []
        excluded_items = []

        for item in items:
            result = self._validator.validate(item)
            if result.is_valid:
                valid_items.append(result)
            else:
                excluded_items.append(result)

        logger.info(
            "Проверка завершена: всего=%d, соответствует=%d, исключений=%d",
            len(items),
            len(valid_items),
            len(excluded_items),
        )
        return BatchVerificationSummary(
            total_processed=len(items),
            valid_items=valid_items,
            excluded_items=excluded_items,
        )

    def process_file(
        self, input_path: Path, output_path: Path
    ) -> BatchVerificationSummary:
        """Загружает каталог из файла, выполняет проверку и сохраняет итоговый Excel-отчет."""
        logger.info("Обработка входного файла каталога: %s", input_path)
        items = self._reader.read(input_path)
        summary = self.verify_items(items)
        self._exporter.export(summary.valid_items, summary.excluded_items, output_path)

        return BatchVerificationSummary(
            total_processed=summary.total_processed,
            valid_items=summary.valid_items,
            excluded_items=summary.excluded_items,
            report_path=output_path,
        )
