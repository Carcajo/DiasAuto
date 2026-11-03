import tempfile
import pandas as pd
import streamlit as st
from pathlib import Path

from src.core.logger import get_logger
from src.core.models import CertificateRuleSet
from src.core.normalizer import SkuNormalizer
from src.core.service import CertificateVerificationService
from src.core.validator import MaskValidator
from src.reports.excel_report import ExcelReportExporter, TabularCatalogReader

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "masks_hilex.yaml"
DEFAULT_SAMPLE_PATH = BASE_DIR / "data" / "sample_catalog.xlsx"


def build_service(
    config_path: Path,
) -> tuple[CertificateVerificationService, CertificateRuleSet]:
    rules = CertificateRuleSet.from_yaml(config_path)
    normalizer = SkuNormalizer()
    validator = MaskValidator(rules=rules, normalizer=normalizer)
    reader = TabularCatalogReader()
    exporter = ExcelReportExporter()
    service = CertificateVerificationService(
        validator=validator,
        reader=reader,
        exporter=exporter,
    )
    return service, rules


def main() -> None:
    st.set_page_config(
        page_title="Верификация масочных сертификатов HI-LEX",
        layout="wide",
    )
    st.title("Система автоматической проверки артикулов по маскам сертификата")

    service, rules = build_service(DEFAULT_CONFIG_PATH)

    with st.expander("Активные правила сертификата", expanded=False):
        st.markdown(f"**Производитель:** `{rules.manufacturer}`")
        st.markdown(f"**Товарная группа:** `{rules.product_group}`")
        st.markdown(
            f"**Количество префиксов в реестре:** `{len(rules.allowed_prefixes)}`"
        )
        st.code(rules.compiled_regex.pattern, language="regex")

    uploaded_file = st.file_uploader(
        "Загрузите каталог номенклатуры (.xlsx или .csv)",
        type=["xlsx", "csv"],
    )

    use_sample = st.checkbox(
        "Использовать демонстрационный каталог (data/sample_catalog.xlsx)",
        value=uploaded_file is None and DEFAULT_SAMPLE_PATH.exists(),
    )

    input_path = None
    temp_dir = None

    if uploaded_file is not None:
        temp_dir = tempfile.TemporaryDirectory()
        input_path = Path(temp_dir.name) / uploaded_file.name
        input_path.write_bytes(uploaded_file.getvalue())
        logger.info("Загружен пользовательский файл через UI: %s", uploaded_file.name)
    elif use_sample and DEFAULT_SAMPLE_PATH.exists():
        input_path = DEFAULT_SAMPLE_PATH

    if input_path is not None:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_out:
            output_path = Path(tmp_out.name)

        summary = service.process_file(input_path=input_path, output_path=output_path)

        col1, col2, col3 = st.columns(3)
        col1.metric("Всего проверено позиций", summary.total_processed)
        col2.metric("Соответствуют сертификату", len(summary.valid_items))
        col3.metric("Направлено в исключения", len(summary.excluded_items))

        tab_valid, tab_excluded = st.tabs(
            [
                f"Соответствуют ({len(summary.valid_items)})",
                f"Исключения ({len(summary.excluded_items)})",
            ]
        )

        with tab_valid:
            if summary.valid_items:
                st.dataframe(
                    pd.DataFrame([vars(item) for item in summary.valid_items]),
                    use_container_width=True,
                )
            else:
                st.info("Нет позиций, удовлетворяющих условиям сертификата.")

        with tab_excluded:
            if summary.excluded_items:
                st.dataframe(
                    pd.DataFrame([vars(item) for item in summary.excluded_items]),
                    use_container_width=True,
                )
            else:
                st.success("Исключений не обнаружено.")

        with output_path.open("rb") as f:
            st.download_button(
                label="Скачать итоговый отчет (.xlsx)",
                data=f.read(),
                file_name="certificate_verification_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


if __name__ == "__main__":
    main()
