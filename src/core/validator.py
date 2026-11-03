import re
from abc import ABC, abstractmethod
from src.core.logger import get_logger
from src.core.models import CatalogItem, CertificateRuleSet, ValidationResult
from src.core.normalizer import BaseNormalizer

logger = get_logger(__name__)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_ALNUM_RE = re.compile(r"^[A-Z0-9]+$")


class BaseValidator(ABC):
    """Абстракция валидатора позиции каталога."""

    @abstractmethod
    def validate(self, item: CatalogItem) -> ValidationResult:
        """Проверяет позицию каталога и возвращает детальный результат."""


class MaskValidator(BaseValidator):
    """
    Валидатор артикулов по правилам масочного сертификата.
    Проверяет производителя, товарную группу, отсутствие спецсимволов/кириллицы,
    длину артикула и вхождение префикса в рабочий реестр.
    """

    def __init__(self, rules: CertificateRuleSet, normalizer: BaseNormalizer) -> None:
        self._rules = rules
        self._normalizer = normalizer
        self._expected_manufacturer = normalizer.normalize_text_field(
            rules.manufacturer
        )
        self._expected_group = normalizer.normalize_text_field(rules.product_group)

    def validate(self, item: CatalogItem) -> ValidationResult:
        search_key = self._normalizer.normalize_sku(item.raw_sku)
        norm_manufacturer = self._normalizer.normalize_text_field(item.manufacturer)
        norm_group = self._normalizer.normalize_text_field(item.product_group)

        # 1. Проверка производителя
        if norm_manufacturer != self._expected_manufacturer:
            reason = f"Несоответствие производителя: '{item.manufacturer}' (ожидается '{self._rules.manufacturer}')"
            logger.debug(
                "Отклонен SKU %r (строка %d): %s", item.raw_sku, item.row_number, reason
            )
            return self._reject(item, search_key, reason)

        # 2. Проверка товарной группы
        if norm_group != self._expected_group:
            reason = f"Несоответствие товарной группы: '{item.product_group}' (ожидается '{self._rules.product_group}')"
            logger.debug(
                "Отклонен SKU %r (строка %d): %s", item.raw_sku, item.row_number, reason
            )
            return self._reject(item, search_key, reason)

        # 3. Быстрая проверка полного соответствия регулярному выражению сертификата
        if self._rules.compiled_regex.fullmatch(search_key):
            prefix = search_key[: self._rules.prefix_length]
            wildcard_count = self._rules.mask_length - self._rules.prefix_length
            matched_mask = f"{prefix}{'*' * wildcard_count}"
            reason = f"Префикс {prefix} и четыре допустимых символа"
            logger.debug("Принят SKU %r -> маска %s", item.raw_sku, matched_mask)
            return ValidationResult(
                raw_sku=item.raw_sku,
                search_key=search_key,
                manufacturer=item.manufacturer,
                product_group=item.product_group,
                is_valid=True,
                matched_mask=matched_mask,
                reason=reason,
                row_number=item.row_number,
            )

        # 4. Детальная диагностика причины исключения
        reason = self._diagnose_failure(search_key)
        logger.debug(
            "Исключение для SKU %r (ключ %r): %s", item.raw_sku, search_key, reason
        )
        return self._reject(item, search_key, reason)

    def _diagnose_failure(self, search_key: str) -> str:
        prefix_len = self._rules.prefix_length
        expected_len = self._rules.mask_length
        prefix = search_key[:prefix_len]

        match search_key:
            case "":
                return "Пустой артикул"

            case s if "\n" in s or "\r" in s:
                return "Недопустимый символ: перевод строки внутри артикула"

            case s if cyrillic_match := _CYRILLIC_RE.search(s):
                return f"Буква {cyrillic_match.group(0)} в строке кириллическая"

            case s if "-" in s:
                return "Дефис внутри артикула"

            case s if "." in s:
                return "Точка внутри артикула"

            case s if " " in s or "\t" in s:
                return "Пробел внутри артикула"

            case s if not _LATIN_ALNUM_RE.fullmatch(s):
                invalid_chars = "".join(sorted({ch for ch in s if not ch.isalnum()}))
                return f"Недопустимые спецсимволы в артикуле: {invalid_chars}"

            case s if len(s) != expected_len and prefix in self._rules.prefix_set:
                suffix_len = max(0, len(s) - prefix_len)
                return (
                    f"Неверная длина ({len(s)} вместо {expected_len}): "
                    f"после префикса {prefix} указано {suffix_len} симв. вместо {expected_len - prefix_len}"
                )

            case s if len(s) != expected_len:
                return f"Неверная длина артикула: {len(s)} симв. (ожидается {expected_len})"

            case _ if prefix not in self._rules.prefix_set:
                return f"Префикс {prefix} отсутствует в перечне"

            case _:
                return "Артикул не соответствует формату маски сертификата"

    @staticmethod
    def _reject(item: CatalogItem, search_key: str, reason: str) -> ValidationResult:
        return ValidationResult(
            raw_sku=item.raw_sku,
            search_key=search_key,
            manufacturer=item.manufacturer,
            product_group=item.product_group,
            is_valid=False,
            matched_mask=None,
            reason=reason,
            row_number=item.row_number,
        )
