from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.core.logger import get_logger
from src.core.models import CatalogItem, ValidationResult

logger = get_logger(__name__)


class BaseCatalogReader(ABC):
    """Абстракция чтения входного каталога товаров."""

    @abstractmethod
    def read(self, file_path: Path) -> list[CatalogItem]:
        """Читает позиции каталога из файла."""


class BaseReportExporter(ABC):
    """Абстракция генератора итогового отчета."""

    @abstractmethod
    def export(
        self,
        valid_items: list[ValidationResult],
        excluded_items: list[ValidationResult],
        output_path: Path,
    ) -> Path:
        """Сохраняет результаты проверки в файл отчета."""


class TabularCatalogReader(BaseCatalogReader):
    """Читает каталог артикулов из файлов Excel (.xlsx) или CSV (.csv)."""

    def __init__(
        self,
        sku_column: str = "Артикул",
        manufacturer_column: str = "Производитель",
        group_column: str = "Товарная группа",
    ) -> None:
        self._sku_col = sku_column
        self._manufacturer_col = manufacturer_column
        self._group_col = group_column

    def read(self, file_path: Path) -> list[CatalogItem]:
        if not file_path.exists():
            logger.error("Входной файл каталога не найден: %s", file_path)
            raise FileNotFoundError(f"Входной файл не найден: {file_path}")

        suffix = file_path.suffix.lower()
        logger.info("Чтение каталога из файла %s (формат %s)", file_path, suffix)

        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, dtype=str, keep_default_na=False)
        elif suffix == ".csv":
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {suffix}")

        missing = [
            col
            for col in (self._sku_col, self._manufacturer_col, self._group_col)
            if col not in df.columns
        ]
        if missing:
            logger.error(
                "В файле %s отсутствуют обязательные колонки: %s", file_path, missing
            )
            raise ValueError(f"Отсутствуют обязательные колонки: {', '.join(missing)}")

        items = []
        for idx, row in df.iterrows():
            items.append(
                CatalogItem(
                    raw_sku=str(row[self._sku_col]),
                    manufacturer=str(row[self._manufacturer_col]),
                    product_group=str(row[self._group_col]),
                    row_number=int(idx) + 2,
                )
            )

        logger.info(
            "Успешно прочитано %d строк из каталога %s", len(items), file_path.name
        )
        return items


class ExcelReportExporter(BaseReportExporter):
    """Формирует двухстраничный Excel-отчет с листами 'Соответствуют' и 'Исключения'."""

    def export(
        self,
        valid_items: list[ValidationResult],
        excluded_items: list[ValidationResult],
        output_path: Path,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Формирование итогового Excel-отчета: %s", output_path)

        valid_df = pd.DataFrame(
            [
                {
                    "№ строки": item.row_number,
                    "Исходный артикул": item.raw_sku,
                    "Поисковый ключ": item.search_key,
                    "Производитель": item.manufacturer,
                    "Товарная группа": item.product_group,
                    "Маска сертификата": item.matched_mask or "",
                    "Комментарий проверки": item.reason,
                }
                for item in valid_items
            ]
        )

        excluded_df = pd.DataFrame(
            [
                {
                    "№ строки": item.row_number,
                    "Исходный артикул": item.raw_sku,
                    "Поисковый ключ": item.search_key,
                    "Производитель": item.manufacturer,
                    "Товарная группа": item.product_group,
                    "Причина исключения": item.reason,
                }
                for item in excluded_items
            ]
        )
        if valid_df.empty:
            valid_df = pd.DataFrame(
                columns=[
                    "№ строки",
                    "Исходный артикул",
                    "Поисковый ключ",
                    "Производитель",
                    "Товарная группа",
                    "Маска сертификата",
                    "Комментарий проверки",
                ]
            )
        if excluded_df.empty:
            excluded_df = pd.DataFrame(
                columns=[
                    "№ строки",
                    "Исходный артикул",
                    "Поисковый ключ",
                    "Производитель",
                    "Товарная группа",
                    "Причина исключения",
                ]
            )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            valid_df.to_excel(writer, sheet_name="Соответствуют", index=False)
            excluded_df.to_excel(writer, sheet_name="Исключения", index=False)

            self._style_worksheet(writer.sheets["Соответствуют"], header_hex="1F4E78")
            self._style_worksheet(writer.sheets["Исключения"], header_hex="843C0C")

        logger.info("Отчет успешно сохранен: %s", output_path)
        return output_path

    @staticmethod
    def _style_worksheet(worksheet, header_hex: str) -> None:
        header_fill = PatternFill(
            start_color=header_hex, end_color=header_hex, fill_type="solid"
        )
        header_font = Font(color="FFFFFF", bold=True)

        for col_idx, column_cells in enumerate(worksheet.columns, start=1):
            max_len = 0
            for row_idx, cell in enumerate(column_cells, start=1):
                if row_idx == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)

            col_letter = get_column_letter(col_idx)
            worksheet.column_dimensions[col_letter].width = min(
                max(max_len + 4, 14), 55
            )
